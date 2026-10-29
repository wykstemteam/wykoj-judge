import logging
import shutil
import subprocess
from typing import List, Optional

import judge.extensions as extensions
from judge.models import SourceFile

from .language import Language

logger = logging.getLogger(__name__)


class CompilationError(Exception):
    pass


"""
Compiles, links and creates executable for the code argument.
Supports multi-file compilation and linking.
"""
def prepare(language: Language, box_id: int, base_name: str, source_files: SourceFile | List[SourceFile], cleanup: bool) -> List[str]:
    if cleanup:
        subprocess.run(['isolate', '-b', str(box_id), '--cleanup'])
        subprocess.run(['isolate', '-b', str(box_id), '--init'], stdout=subprocess.PIPE)

    if isinstance(source_files, SourceFile):
        source_files = [source_files]
    
    sandbox_path = f'/var/local/lib/isolate/{box_id}/box'
    code_filename = [f'{base_name}_{src.filename}.{extensions.file_extensions[language]}' 
                     for src in source_files]
    executable_path = f'run/{base_name}'
    code_path = [f'run/{singular_code_filename}' for singular_code_filename in code_filename]
    
    for singular_code_path, src in zip(code_path, source_files):
        with open(singular_code_path, 'w', encoding='utf-8') as f:
            f.write(src.code)

    compile_args = None
    run_args = None
    if language == Language.cpp:
        compile_args = ['g++', '-O2', '-o', executable_path, *code_path, '--std=c++20' ]
    elif language == Language.c:
        compile_args = ['gcc', '-O2', '-o', executable_path, *code_path, '-lm']
    elif language == Language.ocaml:
        compile_args = ['ocamlopt', '-S', '-o', executable_path, *code_path]
    # elif language == Language.pas:
    #     compile_args = ['fpc', '-O2', '-Sg', '-v0', '-XS', code_path, '-o' + executable_path]
    elif language == Language.py:
        if len(code_filename) > 1:
            raise NotImplementedError("Python does not support non-batch task")
        run_args = ['/usr/bin/python3', code_filename[0]]
    else:
        raise NotImplementedError

    if compile_args:
        # copy source files into the sandbox to compile, 
        # so submission code cannot read test cases
        for path in code_path:
            shutil.copy(path, sandbox_path)

        # compile inside the sandbox
        sandbox_compile_args = [
            arg.replace('run/', '') for arg in compile_args
        ]

        compile_proc = subprocess.run(
            [
                'isolate', '-b', str(box_id),
                '--processes',
                '-w', '60',
                '--run', '--',
                *sandbox_compile_args
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=70
        )

        if compile_proc.returncode != 0:
            logger.error("Compilation failed:")
            logger.error("STDOUT:")
            logger.error(compile_proc.stdout)
            logger.error("STDERR:")
            logger.error(compile_proc.stderr)
            raise CompilationError

        run_args = [base_name]
    else:
        for path in code_path:
            shutil.copy(path, sandbox_path)
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
                          text=True,
                          encoding='utf-8',
                          errors='replace')
