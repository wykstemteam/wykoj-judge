import subprocess
from typing import Union, List

import cachetools
import requests

import compilation
import constants
from language import Language
from task_info import TaskInfo, TestCase
from test_case_result import TestCaseResult
from threads_manager import threads_manager
from verdict import Verdict


@cachetools.cached(cache=cachetools.TTLCache(maxsize=10, ttl=60))
def get_task_info(task_id: str) -> TaskInfo:
    if constants.DEBUG:
        json = {'grader': True, 'grader_language': 'py', 'grader_source_code': '''
import random
import time

random.seed(time.time())

print(random.choice(["AC", "PS 69", "WA"]))
        ''', "memory_limit": 256,
                "test_cases": [{"input": "1 1\n", "output": "Quadrant I\n", "subtask": 1, "test_case": 1},
                               {"input": "-50 -33\n", "output": "Quadrant III\n", "subtask": 1, "test_case": 2},
                               {"input": "94 -87\n", "output": "Quadrant IV\n", "subtask": 1, "test_case": 3},
                               {"input": "-100 100\n", "output": "Quadrant II\n", "subtask": 1, "test_case": 4},
                               {"input": "0 -24\n", "output": "None\n", "subtask": 1, "test_case": 5},
                               {"input": "66 0\n", "output": "None\n", "subtask": 1, "test_case": 6},
                               {"input": "0 0\n", "output": "None\n", "subtask": 1, "test_case": 7}], "time_limit": 1.0}
    else:
        response = requests.get(f'{constants.FRONTEND_URL}/task/{task_id}/info',
                                headers={'X-Auth-Token': constants.CONFIG.get('secret_key')})
        response.raise_for_status()
        json = response.json()

    return TaskInfo(float(json['time_limit']),
                    int(json['memory_limit']),
                    json['grader'],
                    json.get('grader_source_code'),
                    json.get('grader_language'),
                    [TestCase(tc['subtask'],
                              tc['test_case'],
                              tc['input'],
                              tc.get('output')) for tc in json['test_cases']])


def judge(code: str, submission_id: str, task_id: str, language: Language, thread_id: int) -> None:
    threads_manager.add_thread(thread_id)
    verdict = _judge_impl(code, task_id, language, thread_id)

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '-b', str(thread_id), '--cleanup'],
                                  text=True,
                                  stdout=subprocess.PIPE)
    if cleanup_proc.returncode != 0:
        verdict = Verdict.SE
    threads_manager.remove_thread(thread_id)
    if constants.DEBUG:
        print(verdict)
    else:
        report_url = f'{constants.FRONTEND_URL}/submission/{submission_id}/report'
        if type(verdict) is Verdict:
            response = requests.post(report_url,
                                     json={'verdict': verdict},
                                     headers={'X-Auth-Token': constants.CONFIG.get('secret_key')})
        else:
            response = requests.post(report_url,
                                     json={'test_case_results': [{'subtask': v.subtask,
                                                                  'test_case': v.test_case,
                                                                  'verdict': v.verdict,
                                                                  'score': v.score,
                                                                  'time_used': v.time_used,
                                                                  'memory_used': v.memory_used}
                                                                 for v in verdict]},
                                     headers={'X-Auth-Token': constants.CONFIG.get('secret_key')})
        response.raise_for_status()


def _judge_impl(code: str, task_id: str, language: Language, thread_id: int) -> Union[Verdict, List[TestCaseResult]]:
    base_name = f'code{thread_id}'
    metadata_path = f'run/metadata{thread_id}.txt'
    try:
        run_args = compilation.prepare(language, thread_id, base_name, code)
    except compilation.CompilationError:
        return Verdict.CE

    task_info = get_task_info(task_id)
    test_case_results = []
    test_case_outputs = []
    for test_case in task_info.test_cases:
        if test_case.input[:-1] != '\n':
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
                    a, b = line.split(':')
                    metadata[a] = b

        verdict = Verdict.AC
        if 'status' in metadata:
            status = metadata['status']
            if status == 'RE' or status == 'SG' or status == 'XX':
                verdict = Verdict.RE
            elif status == 'TO':
                verdict = Verdict.TLE
            else:
                return Verdict.SE

        test_case_results.append(
            TestCaseResult(subtask=test_case.subtask,
                           test_case=test_case.test_case,
                           verdict=verdict,
                           score=0.,
                           time_used=float(metadata['time']),
                           memory_used=int(metadata['max-rss']) / 1024))
        test_case_outputs.append(run_proc.stdout)

    grader_run_args = []
    if task_info.grader:
        grader_base_name = f'grader{thread_id}'
        grader_run_args = compilation.prepare(task_info.grader_language, thread_id, grader_base_name,
                                              task_info.grader_source_code)
    for i in range(len(test_case_outputs)):
        if test_case_results[i].verdict != Verdict.AC:  # RE, TLE etc.
            continue

        test_case = task_info.test_cases[i]
        output = test_case_outputs[i]
        if output and output[-1] != '\n':  # again ensure output has trailing \n
            output += '\n'
        output = ''.join([line.rstrip() + '\n' for line in output.split('\n')])

        if task_info.grader:
            input_lines_count = test_case.input.count('\n')
            output_lines_count = output.count('\n')
            grader_input = f'{input_lines_count}\n' + f'{test_case.input}\n' + \
                           f'{output_lines_count}\n' + f'{output}\n'
            grader_proc = compilation.run(grader_run_args, thread_id, grader_input)
            if grader_proc.returncode != 0:
                return Verdict.SE
            grader_output = grader_proc.stdout.strip()
            if grader_output == 'WA':
                test_case_results[i].verdict = Verdict.WA
                test_case_results[i].score = 0.
            elif grader_output == 'AC':
                test_case_results[i] = Verdict.AC
                test_case_results[i].score = 100.
            else:  # supposedly is PS
                _, score = grader_output.split()
                test_case_results[i].verdict = Verdict.PS
                test_case_results[i].score = float(score)

        else:
            target_output = test_case.output
            if target_output and target_output[-1] != '\n':  # again ensure output has trailing \n
                target_output += '\n'
            target_output = ''.join([line.rstrip() + '\n' for line in target_output.split('\n')])
            if output != target_output:
                test_case_results[i].verdict = Verdict.WA
                test_case_results[i].score = 0.
            else:
                test_case_results[i].verdict = Verdict.AC
                test_case_results[i].score = 100.

    return test_case_results
