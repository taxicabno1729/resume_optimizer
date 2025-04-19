#!/usr/bin/env python3
import os
import sys
import subprocess
import venv
import platform
import shutil

# Path to virtual environment
VENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")

def is_venv_installed():
    """Check if virtual environment is already installed"""
    return os.path.exists(VENV_PATH)

def create_virtual_environment():
    """Create a new virtual environment"""
    print("Creating virtual environment...")
    venv.create(VENV_PATH, with_pip=True)
    print("Virtual environment created successfully!")

def get_pip_path():
    """Get the path to pip in the virtual environment"""
    if platform.system() == "Windows":
        return os.path.join(VENV_PATH, "Scripts", "pip")
    else:
        return os.path.join(VENV_PATH, "bin", "pip")

def get_python_path():
    """Get the path to python in the virtual environment"""
    if platform.system() == "Windows":
        return os.path.join(VENV_PATH, "Scripts", "python")
    else:
        return os.path.join(VENV_PATH, "bin", "python")

def install_requirements():
    """Install required packages"""
    pip_path = get_pip_path()
    requirements_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    
    print(f"Installing requirements from {requirements_path}...")
    subprocess.run([pip_path, "install", "--upgrade", "pip"], check=False)
    subprocess.run([pip_path, "install", "-r", requirements_path], check=False)
    print("Requirements installed successfully!")

def run_app():
    """Run the Streamlit app"""
    python_path = get_python_path()
    streamlit_module = os.path.join(VENV_PATH, "bin", "streamlit") if platform.system() != "Windows" else os.path.join(VENV_PATH, "Scripts", "streamlit.exe")
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    
    if os.path.exists(streamlit_module):
        cmd = [streamlit_module, "run", app_path]
    else:
        cmd = [python_path, "-m", "streamlit", "run", app_path]
    
    print("Starting Resume ATS Optimizer...")
    # Use shell=True on macOS/Linux to ensure proper shell integration
    if platform.system() != "Windows":
        cmd_str = " ".join(cmd)
        subprocess.run(cmd_str, shell=True)
    else:
        subprocess.run(cmd)

def main():
    """Main function to setup and run the application"""
    try:
        # Check if virtual environment exists
        if not is_venv_installed():
            create_virtual_environment()
            install_requirements()
        
        # Run the application
        run_app()
    except Exception as e:
        print(f"Error: {str(e)}")
        print("\nIf you're experiencing issues, try running these commands manually:")
        print("1. python -m venv venv")
        print("2. source venv/bin/activate  # On Windows: venv\\Scripts\\activate")
        print("3. pip install -r requirements.txt")
        print("4. streamlit run app.py")
        sys.exit(1)

if __name__ == "__main__":
    main() 