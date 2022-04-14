import time
import logging
import requests
import subprocess
import traceback
from typing import List, Union

import compilation
import constants
from language import Language
from task_info_manager import TaskInfoManager
from test_case_result import TestCaseResult
from verdict import Verdict


def judge(
        code: str, submission_id: str, language: Language, task_info_path: str, process_id: int
) -> None:
    verdict = _judge_impl(code, language, task_info_path, process_id)

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '-b', str(process_id), '--cleanup'],
                                  text=True,
                                  stdout=subprocess.PIPE)
    if cleanup_proc.returncode != 0:
        verdict = Verdict.SE
    if constants.DEBUG:
        print(verdict)
    else:
        report_url = f'{constants.FRONTEND_URL}/submission/{submission_id}/report'
        if type(verdict) is Verdict:
            response = requests.post(report_url,
                                     json={'verdict': verdict},
                                     headers={'X-Auth-Token': constants.CONFIG['secret_key']})
        else:
            while True:
                try:
                    response = requests.post(report_url,
                                             json={'test_case_results': [{'subtask': v.subtask,
                                                                          'test_case': v.test_case,
                                                                          'verdict': v.verdict,
                                                                          'score': v.score,
                                                                          'time_used': v.time_used,
                                                                          'memory_used': v.memory_used}
                                                                         for v in verdict]},
                                             headers={'X-Auth-Token': constants.CONFIG['secret_key']})
                    break
                except requests.exceptions.ConnectionError:
                    pass
        response.raise_for_status()


def _judge_impl(code: str, language: Language, task_info_path: str,
                process_id: int) -> Union[Verdict, List[TestCaseResult]]:
    start_time = time.perf_counter()

    base_name = f'code{process_id}'
    metadata_path = f'run/metadata{process_id}.txt'
    logging.info(f'process {process_id}: compiling')

    try:
        run_args = compilation.prepare(language, process_id, base_name, code)
    except compilation.CompilationError:
        return Verdict.CE

    try:
        task_info = TaskInfoManager.get_task_info(task_info_path)
    except Exception as e:
        logging.error(
            f'Error in retrieving task info:\n' +
            ''.join(traceback.format_exception(
                etype=type(e), value=e, tb=e.__traceback__))
        )
        return Verdict.SE

    grader_run_args = []
    if task_info.grader:
        grader_base_name = f'grader{process_id}'
        try:
            grader_run_args = compilation.prepare(task_info.grader_language, process_id, grader_base_name,
                                                  task_info.grader_source_code)
        except compilation.CompilationError:
            logging.error(f'process {process_id}: grader compilation error')
            return Verdict.SE

    logging.info(f'process {process_id}: running and judging')
    test_case_results = []
    for test_case in TaskInfoManager.iter_test_cases(task_info_path):
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
                logging.error(f'process {process_id}: isolate funny')
                return Verdict.SE

        test_case_result = TestCaseResult(
            subtask=test_case.subtask,
            test_case=test_case.test_case,
            verdict=verdict,
            score=0.,
            time_used=min(
                float(metadata['time']), task_info.time_limit),
            memory_used=int(metadata['max-rss']) / 1024)

        if test_case_result.verdict == Verdict.AC: # if no tle and stuff
            output = run_proc.stdout
            if not output.endswith('\n'):  # again ensure output has trailing \n
                output += '\n'
            output = ''.join(
                [line.rstrip() + '\n' for line in output.split('\n')])

            if task_info.grader:
                input_lines_count = test_case.input.count('\n')
                output_lines_count = output.count('\n')
                grader_input = (
                    f'{input_lines_count}\n' +
                    f'{test_case.input}'  # including trailing \n
                    f'{output_lines_count}\n' + \
                    f'{output}'
                )
                grader_proc = compilation.run(
                    grader_run_args, process_id, grader_input)
                if grader_proc.returncode != 0:
                    logging.error(f'process {process_id}: grader exited with non-zero code')
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
                        logging.error(f'process {process_id}: grader output error')
                        return Verdict.SE

            else:
                target_output = test_case.output
                # again ensure output has trailing \n
                if not target_output.endswith('\n'):
                    target_output += '\n'
                target_output = ''.join(
                    [line.rstrip() + '\n' for line in target_output.split('\n')])
                if output == target_output:
                    test_case_result.verdict = Verdict.AC
                    test_case_result.score = 100.0
                else:
                    test_case_result.verdict = Verdict.WA
                    test_case_result.score = 0.0
        
        test_case_results.append(test_case_result)

    end_time = time.perf_counter()
    logging.info(f'process {process_id}: completed in {end_time - start_time:.4f}s')
    return test_case_results
