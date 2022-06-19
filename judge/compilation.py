import logging
import shutil
import subprocess
from typing import List, Optional

import judge.extensions as extensions

from .language import Language

logger = logging.getLogger(__name__)


class CompilationError(Exception):
    pass


def prepare(language: Language, box_id: int, base_name: str, code: str, cleanup: bool) -> List[str]:
    if cleanup:
        subprocess.run(['isolate', '-b', str(box_id), '--silent', '--cleanup'])
        subprocess.run(['isolate', '-b', str(box_id), '--silent', '--init'], stdout=subprocess.PIPE)

    sandbox_path = f'/var/local/lib/isolate/{box_id}/box'
    code_filename = f'{base_name}.{extensions.file_extensions[language]}'
    executable_path = f'run/{base_name}'
    code_path = f'run/{code_filename}'
    with open(code_path, 'w') as f:
        f.write(code)

    compile_args = None
    run_args = None
    if language == Language.cpp:
        compile_args = ['g++', '-O2', '-o', executable_path, code_path, '--std=c++17' ]
    elif language == Language.c:
        compile_args = ['gcc', '-O2', '-o', executable_path, code_path]
    elif language == Language.ocaml:
        compile_args = ['ocamlopt', '-S', '-o', executable_path, code_path]
    # elif language == Language.pas:
    #     compile_args = ['fpc', '-O2', '-Sg', '-v0', '-XS', code_path, '-o' + executable_path]
    elif language == Language.py:
        run_args = ['/usr/bin/python3', code_filename]
    else:
        raise NotImplementedError

    if compile_args:
        compile_proc = subprocess.run(compile_args, text=True, stderr=subprocess.PIPE)
        if compile_proc.returncode != 0:
            raise CompilationError
        shutil.copy(executable_path, sandbox_path)  # copies executable to sandbox
        if not run_args:
            run_args = [base_name]  # run by directly calling the name of executable
    else:
        shutil.copy(code_path, sandbox_path)
    return run_args


def run(run_args: List[str], box_id: int, input_: str,
        metadata_path: Optional[str] = None,
        time_limit: Optional[float] = None,
        memory_limit: Optional[int] = None) -> subprocess.CompletedProcess:

    args = ['isolate']
    if metadata_path:
        args += ['-M', metadata_path]
    if box_id:
        args += ['-b', str(box_id)]
    if time_limit:
        args += ['-t', str(time_limit)]
        args += ['-w', str(20)]  # wall time
    if memory_limit:
        args += ['-m', str(memory_limit * 1024)]  # in kB
    args += ['--stderr-to-stdout', '--silent', '--run', '--']
    args += run_args

    logger.debug(' '.join(args))
    return subprocess.run(args,
                          input=input_,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True)
