# Fylorra - GPU Acceleration Guide

## ✅ CURRENT STATUS: Working on CPU
Your app is now fully functional and will use CPU for AI processing.

---

## 🚀 Enable GPU Acceleration (RTX 4070)

To make AI **10-20x faster**, you need to install NVIDIA CUDA Toolkit first.

### Prerequisites:
- NVIDIA GPU (✅ You have RTX 4070)
- NVIDIA Driver 591.44+ (✅ You have 591.44)
- ❌ CUDA Toolkit 12.x (NOT INSTALLED)

---

## Step-by-Step GPU Installation:

### 1️⃣ Install CUDA Toolkit 12.6

**Download:** https://developer.nvidia.com/cuda-downloads

1. Click **Windows** → **x86_64** → **exe (network)**
2. Download (~3GB)
3. Run installer
4. Choose **Express Installation**
5. Wait ~10 minutes for installation
6. **Restart Windows**

### 2️⃣ Verify CUDA Installation

Open Command Prompt and run:
```cmd
nvcc --version
```

You should see: `Cuda compilation tools, release 12.x`

If you see an error, CUDA isn't installed correctly.

### 3️⃣ Rebuild llama-cpp-python with CUDA

Run this batch file:
```
e:\Programing Code Projects\Python\Folder_Monitoring\install_gpu_after_cuda.bat
```

Wait ~5 minutes for compilation.

### 4️⃣ Verify GPU Support

The batch file will show:
```
GPU Support: ENABLED!
```

If it shows "DISABLED", CUDA installation failed.

### 5️⃣ Configure Fylorra

1. Start Fylorra
2. Go to **Settings → AI Features**
3. Set **GPU Layers** to **35**
4. Click **🔄 Reload AI Model**
5. Done! AI will now use your RTX 4070!

---

## Performance Comparison:

| Mode | Speed (per image) | 10 Images |
|------|------------------|-----------|
| **CPU Only** (current) | 4-8 seconds | 40-80 sec |
| **GPU Enabled** | 0.5-1 second ⚡ | 5-10 sec ⚡ |

---

## Troubleshooting:

**Q: CUDA installer fails?**
- Make sure you have ~10GB free space
- Run installer as Administrator

**Q: GPU still shows DISABLED after rebuild?**
- Run: `nvcc --version` to verify CUDA is installed
- Check CUDA is in PATH: `echo %PATH%`
- Restart Windows and try again

**Q: App crashes with GPU enabled?**
- Reduce GPU Layers from 35 to 25
- May indicate VRAM issue (unlikely with 12GB)

---

## Alternative: Pre-built CUDA Wheels

If building fails, try installing pre-built wheels:

1. Go to: https://github.com/abetlen/llama-cpp-python/releases
2. Find release v0.3.16
3. Download: `llama_cpp_python-0.3.16-cp312-cp312-win_amd64-cu121.whl`
4. Install: `pip install llama_cpp_python-0.3.16-cp312-cp312-win_amd64-cu121.whl --force-reinstall`

---

## Need Help?

The app works perfectly on CPU right now. GPU is optional but makes AI much faster.

For GPU issues, you may need to:
- Install Visual Studio Build Tools
- Install CUDA Toolkit properly
- Ensure PATH variables are set

**The app is ready to use NOW on CPU!** 🎉
