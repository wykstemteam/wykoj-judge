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
        code: str, submission_id: str, language: Language, task_info_path: str, thread_id: int
) -> None:
    verdict = _judge_impl(code, language, task_info_path, thread_id)

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '-b', str(thread_id), '--cleanup'],
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
                thread_id: int) -> Union[Verdict, List[TestCaseResult]]:
    base_name = f'code{thread_id}'
    metadata_path = f'run/metadata{thread_id}.txt'
    logging.info(f'thread {thread_id}: compiling')
    try:
        run_args = compilation.prepare(language, thread_id, base_name, code)
    except compilation.CompilationError:
        return Verdict.CE

    try:
        task_info = TaskInfoManager.get_task_info(task_info_path)
    except Exception as e:
        print(
            f'Error in retrieving task info:\n' +
            ''.join(traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__))
        )
        return Verdict.SE

    logging.info(f'thread {thread_id}: running')
    test_case_results = []
    test_case_outputs = []
    for test_case in TaskInfoManager.iter_test_cases(task_info_path):
        if not test_case.input.endswith('\n'):
            test_case.input += '\n'  # ensures input has trailing \n
        run_proc = compilation.run(run_args,
                                   thread_id,
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
                return Verdict.SE

        test_case_results.append(
            TestCaseResult(subtask=test_case.subtask,
                           test_case=test_case.test_case,
                           verdict=verdict,
                           score=0.,
                           time_used=min(float(metadata['time']), task_info.time_limit),
                           memory_used=int(metadata['max-rss']) / 1024))
        test_case_outputs.append(run_proc.stdout)

    logging.info(f'thread {thread_id}: judging')
    grader_run_args = []
    if task_info.grader:
        grader_base_name = f'grader{thread_id}'
        grader_run_args = compilation.prepare(task_info.grader_language, thread_id, grader_base_name,
                                              task_info.grader_source_code)
    for test_case, test_case_result, output in zip(
            TaskInfoManager.iter_test_cases(task_info_path), test_case_results, test_case_outputs
    ):
        if test_case_result.verdict != Verdict.AC:  # RE, TLE etc.
            continue

        if not output.endswith('\n'):  # again ensure output has trailing \n
            output += '\n'
        output = ''.join([line.rstrip() + '\n' for line in output.split('\n')])

        if task_info.grader:
            input_lines_count = test_case.input.count('\n')
            output_lines_count = output.count('\n')
            grader_input = (
                    f'{input_lines_count}\n' + f'{test_case.input}'  # including trailing \n
                                               f'{output_lines_count}\n' + f'{output}'
            )
            grader_proc = compilation.run(grader_run_args, thread_id, grader_input)
            if grader_proc.returncode != 0:
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
                    return Verdict.SE

        else:
            target_output = test_case.output
            if not target_output.endswith('\n'):  # again ensure output has trailing \n
                target_output += '\n'
            target_output = ''.join([line.rstrip() + '\n' for line in target_output.split('\n')])
            if output == target_output:
                test_case_result.verdict = Verdict.AC
                test_case_result.score = 100.0
            else:
                test_case_result.verdict = Verdict.WA
                test_case_result.score = 0.0

    logging.info(f'thread {thread_id}: completed')
    return test_case_results
