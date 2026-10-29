import logging
import subprocess
import time
import traceback
import uuid
from pathlib import Path
from typing import List, Union

import judge.compilation as compilation
import judge.constants as constants

from .common import session
from .models import TaskType, SourceFile, JudgeRequest, TestCaseResult
from .test_case_manager import TestCaseManager
from .verdict import Verdict

logger = logging.getLogger(__name__)


def judge(judge_request: JudgeRequest, process_id: int) -> None:
    try:
        verdict = _judge_impl(judge_request, process_id)
    except Exception as e:
        # Ensures a report is always sent, even on an unexpected bug in
        # _judge_impl, so a submission never gets stuck pending forever.
        logger.error(
            f'process {process_id}: unexpected error while judging:\n' +
            ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        )
        verdict = Verdict.SE

    # cleanup sandboxes
    box_ids = [process_id * 2]
    if judge_request.task_type == TaskType.BATCH and judge_request.task_info.grader:
        box_ids.append(process_id * 2 + 1)

    for box_id in box_ids:
        cleanup_proc = subprocess.run(['isolate', '-b', str(box_id), '--cleanup'])
        if cleanup_proc.returncode != 0:
            logger.error(f'process {process_id} (box {box_id}): failed to clean up sandbox')
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
    
    HAS_BATCH_GRADER = judge_request.task_type == TaskType.BATCH and task_info.grader
    if judge_request.task_type == TaskType.INTERACTIVE and not task_info.grader:
        raise ValueError("Missing grader for interactive tasks")

    base_name = f'code{process_id}'
    metadata_path = f'run/metadata{process_id}.txt'
    secret_key = None
    logger.info(f'process {process_id}: compiling')
    
    submission_box_id = process_id * 2
    grader_box_id = process_id * 2 + 1

    try:
        if judge_request.task_type == TaskType.BATCH:
            run_args = compilation.prepare(
                submission.language,
                submission_box_id,
                base_name,
                SourceFile("submission", submission.source_code),
                cleanup=True
            )
        elif judge_request.task_type == TaskType.INTERACTIVE:
            secret_key = str(uuid.uuid4())
            template = (
                Path("judge/templates") / "interactive_runner_cpp.in"
            ).read_text(encoding="utf-8")
            
            interactive_runner_source_code = template.replace(
                "%secret_key_constant%",
                f'"{secret_key}"'
            )
            
            run_args = compilation.prepare(
                submission.language,
                submission_box_id,
                base_name,
                [ SourceFile("submission", submission.source_code),
                  SourceFile("grader", task_info.grader_source_code),
                  SourceFile("runner", interactive_runner_source_code) ],
                cleanup=True
            )
        else:
            raise NotImplementedError
    except compilation.CompilationError:
        return Verdict.CE

    grader_run_args = []
    if HAS_BATCH_GRADER:
        grader_base_name = f'grader{process_id}'
        try:
            grader_run_args = compilation.prepare(
                task_info.grader_language,
                grader_box_id,
                grader_base_name,
                SourceFile("batch_grader", task_info.grader_source_code),
                cleanup=True
            )
        except compilation.CompilationError:
            logger.error(f'process {process_id} (box {grader_box_id}): grader compilation error')
            return Verdict.SE

    logger.info(f'process {process_id} (box {submission_box_id}): running and judging')
    test_case_results = []
    test_cases_generator = TestCaseManager.iter_test_cases(task_info)
    reverse_dependencies = {}

    if task_info.dependencies:
        for st, dependencies in task_info.dependencies.items():
            for future_st in dependencies:
                reverse_dependencies.setdefault(int(future_st), []).append(int(st))

    try:
        # Only ever advance test_cases_generator once per loop iteration,
        # via next() to prime it and .send() thereafter, since .send()
        # both resumes the generator AND passes in newly-skipped subtasks.
        test_case = next(test_cases_generator)
        while True:
            if not test_case.skip:
                if not test_case.input.endswith('\n'):
                    test_case.input += '\n'  # ensures input has trailing \n
                run_proc = compilation.run(run_args,
                                        submission_box_id,
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
            else:
                metadata = {
                    'status': 'SK',
                    'time': 0.0,
                    'max-rss': 0
                }

            verdict = Verdict.AC
            if 'status' in metadata:
                status = metadata['status']
                if status in ('RE', 'SG'):
                    verdict = Verdict.RE
                elif status == 'TO':
                    verdict = Verdict.TLE
                elif status == 'SK':
                    verdict = Verdict.SK
                else:  # Including status == 'XX'
                    logger.error(f'process {process_id} (box {submission_box_id}): isolate funny')
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
                    if HAS_BATCH_GRADER:
                        input_lines_count = test_case.input.count('\n')
                        output_lines_count = output.count('\n')
                        grader_input = (
                            f'{input_lines_count}\n'
                            + test_case.input  # including trailing \n
                            + f'{output_lines_count}\n'
                            + output
                        )
                        grader_proc = compilation.run(grader_run_args, grader_box_id, grader_input)
                        if grader_proc.returncode != 0:
                            logger.error(f'process {process_id} (box {grader_box_id}): grader exited with non-zero code')
                            return Verdict.SE

                        grader_output = grader_proc.stdout.strip()
                    else:
                        raw_grader_output = output.strip().splitlines()

                        if len(raw_grader_output) != 2:
                            return Verdict.SV

                        returned_secret, grader_output = raw_grader_output

                        if returned_secret != secret_key:
                            return Verdict.SV
                    
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
                            logger.error(f'process {process_id} (box {submission_box_id}): grader output error')
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

            send_value = None
            if (test_case_result.verdict != Verdict.AC and 
                    test_case_result.verdict != Verdict.PS) and test_case.subtask in reverse_dependencies:
                send_value = reverse_dependencies.pop(test_case.subtask)

            test_case_results.append(test_case_result)
            test_case = test_cases_generator.send(send_value)
    except StopIteration:
        pass

    end_time = time.perf_counter()
    logger.info(f'process {process_id}: completed in {end_time - start_time:.4f}s')
    return test_case_results
