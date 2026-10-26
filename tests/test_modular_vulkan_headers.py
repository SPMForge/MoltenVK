"""Compile staged Vulkan headers with a C++ standard-library module boundary."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('materialize', ROOT / 'scripts/spm/materialize_public_headers.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ModularVulkanHeadersTests(unittest.TestCase):
    def test_system_header_imports_remain_outside_c_linkage(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'stdint.h').write_text('#pragma once\ntypedef unsigned int uint32_t;\n')
            (root / 'module.modulemap').write_text('module std_stdint_h { requires cplusplus header "stdint.h" export * }\n')
            headers = root / 'headers'
            headers.mkdir()
            header = headers / 'vk_platform.h'
            header.write_text('#pragma once\n#ifdef __cplusplus\nextern "C" {\n#endif\n'
                              '#if !defined(VK_NO_STDINT_H)\n#include <stdint.h>\n#endif\n'
                              '#ifdef __cplusplus\n}\n#endif\n')
            module.rewrite_framework_includes(headers)
            source = root / 'probe.cpp'
            source.write_text('#include "headers/vk_platform.h"\nuint32_t value;\n')
            result = subprocess.run([compiler, '-std=c++17', '-Werror=module-import-in-extern-c', '-fmodules', '-fcxx-modules',
                                     '-fmodules-cache-path=' + str(root / 'cache'), '-I', str(root),
                                     '-fmodule-map-file=' + str(root / 'module.modulemap'), '-nostdinc', '-fsyntax-only', str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The patch must preserve C importability as well as C++ module importability.
            result = subprocess.run([compiler, '-x', 'c', '-I', str(root), '-fsyntax-only', str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
