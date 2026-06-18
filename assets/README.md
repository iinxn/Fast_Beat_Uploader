# assets

Положи сюда `icon.ico`, чтобы у собранного `FastBeatsRender.exe` была своя иконка.

Сборка (`FastBeatsRender.spec`) подхватывает `assets/icon.ico` автоматически —
если файла нет, используется стандартная иконка PyInstaller.

Конвертация PNG → ICO (нужен Pillow):

```powershell
.\.venv\Scripts\python.exe -m pip install pillow
.\.venv\Scripts\python.exe -c "from PIL import Image; Image.open('icon.png').save('assets/icon.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
```
