
import os
import subprocess
import sys

def build():
    print("=== BIST Terminal Builder ===")
    
    # Bağımlılık kontrolü
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller bulunamadı. Kuruluyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Build komutu
    # --onefile: Tek dosya
    # --noconsole: Terminal penceresini gizle
    # --name: Exe adı
    # --add-data: Ek dosyalar (logo, config vb. varsa eklenebilir)
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        "--name", "BIST_Terminal",
        "--clean",
        "main.py"
    ]
    
    print(f"Build başlatılıyor: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\n=== Başarılı! ===")
        print("Executable dosyasını 'dist/BIST_Terminal.exe' konumunda bulabilirsin.")
    except Exception as e:
        print(f"\nHata oluştu: {e}")

if __name__ == "__main__":
    build()
