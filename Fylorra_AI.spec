# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

# Get paths for GPU dependencies
cuda_path = r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin'
llama_cpp_path = Path(r'C:\Python312\Lib\site-packages\llama_cpp')

# Collect all CUDA DLLs needed for GPU support
cuda_binaries = []
if os.path.exists(cuda_path):
    for dll in ['cudart64_12.dll', 'cublas64_12.dll', 'cublasLt64_12.dll']:
        dll_path = os.path.join(cuda_path, dll)
        if os.path.exists(dll_path):
            cuda_binaries.append((dll_path, '.'))

# Collect llama_cpp DLLs
llama_binaries = []
if llama_cpp_path.exists():
    lib_path = llama_cpp_path / 'lib'
    if lib_path.exists():
        for dll in lib_path.glob('*.dll'):
            llama_binaries.append((str(dll), 'llama_cpp/lib'))

# Collect all llama_cpp package files
llama_datas = []
if llama_cpp_path.exists():
    for file in llama_cpp_path.rglob('*'):
        if file.is_file() and not file.suffix == '.pyc':
            rel_path = file.relative_to(llama_cpp_path.parent)
            llama_datas.append((str(file), str(rel_path.parent)))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=cuda_binaries + llama_binaries,
    datas=[('assets', 'assets')] + llama_datas,
    hiddenimports=[
        'llama_cpp',
        'llama_cpp.llama_cpp',
        'llama_cpp.llama',
        'llama_cpp.llama_chat_format',
        'llama_cpp._ctypes_extensions',
        'huggingface_hub',
        'huggingface_hub.hf_api',
        'huggingface_hub.file_download',
        'tqdm',
        'requests',
        'filelock',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchvision',
        'torchaudio',
        'transformers',
        'bitsandbytes',
        'accelerate',
        'qwen_vl_utils',
        'tensorflow',
        'tensorboard',
        'cv2',
        'scipy',
        'matplotlib',
        'pandas',
        'pytest',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Fylorra_AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\fylorra.ico'],
)
