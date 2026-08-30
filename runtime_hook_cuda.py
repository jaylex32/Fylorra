"""
PyInstaller runtime hook to fix numpy and add CUDA DLLs to PATH
"""
import os
import sys

# When running from frozen .exe, add the extracted temp dir to PATH
# so torch can find CUDA DLLs
if getattr(sys, 'frozen', False):
    # Get the temporary directory where PyInstaller extracts files
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

    # Add bundle dir to PATH so CUDA DLLs can be found
    if bundle_dir not in os.environ['PATH']:
        os.environ['PATH'] = bundle_dir + os.pathsep + os.environ['PATH']

    # Also add llama_cpp/lib directory
    llama_lib = os.path.join(bundle_dir, 'llama_cpp', 'lib')
    if os.path.exists(llama_lib) and llama_lib not in os.environ['PATH']:
        os.environ['PATH'] = llama_lib + os.pathsep + os.environ['PATH']

    # FIX: Prevent numpy CPU dispatcher from initializing twice
    # This must happen BEFORE numpy is imported
    os.environ['MKL_NUM_THREADS'] = '1'
    os.environ['NUMEXPR_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'

    # Prevent multiple numpy imports by ensuring it's only imported once
    if 'numpy' not in sys.modules:
        try:
            import numpy._core
            import numpy._core.multiarray
            import numpy._core._multiarray_umath
        except Exception:
            pass
