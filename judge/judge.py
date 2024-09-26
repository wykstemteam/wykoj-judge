import logging
import subprocess
import time
from typing import List, Union

import judge.compilation as compilation
import judge.constants as constants

from .common import session
from .models import JudgeRequest, TestCaseResult
from .test_case_manager import TestCaseManager
from .verdict import Verdict

logger = logging.getLogger(__name__)


def judge(judge_request: JudgeRequest, process_id: int) -> None:
    verdict = _judge_impl(judge_request, process_id)

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '-b', str(process_id), '--cleanup'],
                                  text=True,
                                  stdout=subprocess.PIPE)
    if cleanup_proc.returncode != 0:
        verdict = Verdict.SE

    logger.debug(verdict)
    if not constants.DEBUG:
        submission_id = judge_request.submission.id
        report_url = f'{constants.FRONTEND_URL}/submission/{submission_id}/report'
        if type(verdict) is Verdict:
            response = session.post(report_url, json={'verdict': verdict})
        else:
            response = session.post(
                report_url,
                json={'test_case_results': [v.to_dict() for v in verdict]}
            )
        response.raise_for_status()


def _judge_impl(judge_request: JudgeRequest, process_id: int) -> Union[Verdict, List[TestCaseResult]]:
    start_time = time.perf_counter()

    task_info = judge_request.task_info
    submission = judge_request.submission

    base_name = f'code{process_id}'
    metadata_path = f'run/metadata{process_id}.txt'
    logger.info(f'process {process_id}: compiling')

    try:
        run_args = compilation.prepare(
            submission.language,
            process_id,
            base_name,
            submission.source_code,
            cleanup=True
        )
    except compilation.CompilationError:
        return Verdict.CE

    grader_run_args = []
    if task_info.grader:
        grader_base_name = f'grader{process_id}'
        try:
            grader_run_args = compilation.prepare(
                task_info.grader_language,
                process_id,
                grader_base_name,
                task_info.grader_source_code,
                cleanup=False
            )
        except compilation.CompilationError:
            logger.error(f'process {process_id}: grader compilation error')
            return Verdict.SE

    logger.info(f'process {process_id}: running and judging')
    test_case_results = []
    skipped_subtasks = set()
    for test_case in TestCaseManager.iter_test_cases(task_info):
        if submission.in_ongoing_contest and test_case.subtask in skipped_subtasks:
            test_case_result = TestCaseResult(
                subtask=test_case.subtask,
                test_case=test_case.test_case,
                verdict=Verdict.SK,
                score=0.0,
                time_used=0.0,
                memory_used=0.0)
            test_case_results.append(test_case_result)
            continue
        
        if not test_case.input.endswith('\n'):
            test_case.input += '\n'  # ensures input has trailing \n
        run_proc = compilation.run(run_args,
                                   process_id,
                                   test_case.input,
                                   metadata_path,
                                   task_info.time_limit,
                                   task_info.memory_limit)

        metadata = {}
        with open(metadata_path) as f:
            for line in f.readlines():
                line = line.strip()
                if line:
                    a, b = line.split(':', maxsplit=1)
                    metadata[a] = b

        verdict = Verdict.AC
        if 'status' in metadata:
            status = metadata['status']
            if status in ('RE', 'SG'):
                verdict = Verdict.RE
            elif status == 'TO':
                verdict = Verdict.TLE
            else:  # Including status == 'XX'
                logger.error(f'process {process_id}: isolate funny')
                return Verdict.SE

        test_case_result = TestCaseResult(
            subtask=test_case.subtask,
            test_case=test_case.test_case,
            verdict=verdict,
            score=0.0,
            time_used=min(float(metadata['time']), task_info.time_limit),
            memory_used=int(metadata['max-rss']) / 1024)

        if verdict == Verdict.AC:  # if no tle and stuff
            output = run_proc.stdout
            if not output.endswith('\n'):  # again ensure output has trailing \n
                output += '\n'
            output = ''.join(
                [line.rstrip() + '\n' for line in output.split('\n')])

            if task_info.grader:
                input_lines_count = test_case.input.count('\n')
                output_lines_count = output.count('\n')
                grader_input = (
                    f'{input_lines_count}\n'
                    + test_case.input  # including trailing \n
                    + f'{output_lines_count}\n'
                    + output
                )
                grader_proc = compilation.run(grader_run_args, process_id, grader_input)
                if grader_proc.returncode != 0:
                    logger.error(f'process {process_id}: grader exited with non-zero code')
                    return Verdict.SE

                grader_output = grader_proc.stdout.strip()
                if grader_output == 'AC':
                    test_case_result.verdict = Verdict.AC
                    test_case_result.score = 100.0
                elif grader_output == 'WA':
                    test_case_result.verdict = Verdict.WA
                    test_case_result.score = 0.0
                else:  # Assume is PS
                    try:
                        verdict, score = grader_output.split(maxsplit=1)
                        assert verdict == "PS"
                        test_case_result.verdict = Verdict.PS
                        test_case_result.score = float(score)
                        assert 0 <= test_case_result.score <= 100
                    except (ValueError, AssertionError):
                        logger.error(f'process {process_id}: grader output error')
                        return Verdict.SE
            else:
                target_output = test_case.output
                # again ensure output has trailing \n
                if not target_output.endswith('\n'):
                    target_output += '\n'
                target_output = ''.join([line.rstrip() + '\n' for line in target_output.split('\n')])
                if output == target_output:
                    test_case_result.verdict = Verdict.AC
                    test_case_result.score = 100.0
                else:
                    test_case_result.verdict = Verdict.WA
                    test_case_result.score = 0.0
                    
        if submission.in_ongoing_contest and test_case_result.verdict != Verdict.AC:
            skipped_subtasks.add(test_case.subtask)

        test_case_results.append(test_case_result)

    end_time = time.perf_counter()
    logger.info(f'process {process_id}: completed in {end_time - start_time:.4f}s')
    return test_case_results
