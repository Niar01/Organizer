# ESPAÑOL  
  # Downloads Organizer

Script en Python que vigila `~/Downloads` y clasifica cada archivo en subcarpetas
según su tipo (Documentos, Imagenes, Comprimidos, etc.). Espera un tiempo
configurable (5 minutos por defecto) y verifica que el tamaño del archivo sea
estable antes de moverlo, para no mover descargas a medias.

El proyecto vive en `~/Downloads/Downloads-organizer/`. Como el script solo
organiza archivos sueltos del nivel superior de `~/Downloads` (y esta carpeta es
una subcarpeta), nunca mueve ni altera sus propios archivos.

## Instalación de dependencias

La única dependencia es `watchdog`.

- Con pacman (recomendado en Arch):
  ```
  sudo pacman -S python-watchdog
  ```
- Con pip:
  ```
  pip install --user -r requirements.txt
  ```

## Configuración (opcional)

Todo funciona con valores por defecto embebidos en el script. Para personalizar:

```
mkdir -p ~/.config/downloads-organizer
cp config.json.example ~/.config/downloads-organizer/config.json
```

Opciones del JSON:

| Clave               | Descripción                                            | Defecto        |
|---------------------|--------------------------------------------------------|----------------|
| `downloads_dir`     | Carpeta a vigilar                                      | `~/Downloads`  |
| `delay_seconds`     | Espera tras el último cambio antes de mover            | `300`          |
| `sample_interval`   | Segundos entre las dos mediciones de tamaño            | `3`            |
| `max_retries`       | Reintentos si el tamaño sigue cambiando                | `5`            |
| `extensions`        | Mapeo categoría → extensiones (llave = nombre de la carpeta) | (listado) |
| `other_category`    | Carpeta para extensiones no listadas                   | `Otros`        |
| `ignore_extensions` | Extensiones que nunca se mueven (descargas en curso)   | `.part`, `.crdownload`, `.tmp` |

Las extensiones se comparan sin distinguir mayúsculas. `config.json` no admite
comentarios; usa `config.json.example` como plantilla.

## Probar en modo manual

```
python3 organizer.py
python3 organizer.py --delay 10 --quiet      # sin mensajes en consola
```

Opciones CLI: `--config RUTA`, `--delay SEGUNDOS`, `--quiet`.

## Servicio systemd (en segundo plano)

```
cp downloads-organizer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now downloads-organizer.service
```

- Estado: `systemctl --user status downloads-organizer.service`
- Ver logs en vivo: `journalctl --user -u downloads-organizer.service -f`
- Log propio (rotativo): `~/.local/share/downloads-organizer/organizer.log`
- Deshabilitar: `systemctl --user disable --now downloads-organizer.service`

El servicio se inicia al iniciar sesión y se reinicia automáticamente si falla.

## Comportamiento

- Solo se organizan archivos sueltos en el nivel superior de `~/Downloads`
  (las subcarpetas, incluidas las de categoría, no se tocan).
- Se ignoran archivos ocultos (`.`), los de `ignore_extensions` y las carpetas
  de categoría (sin bucles).
- Colisiones: en vez de sobrescribir, se genera `archivo(1).txt`, `archivo(2).txt`, etc.
- Si un archivo desaparece antes de moverse, o hay errores de permisos/I/O,
  se registra en el log y el servicio continúa.
  
  
  
  # English 
  
  
  # Downloads Organizer

A Python script that monitors `~/Downloads` and organizes each file into subfolders based on its type (Documents, Images, Compressed, etc.). It waits for a configurable period (5 minutes by default) and verifies that the file size remains stable before moving it, preventing partial downloads from being moved.

The project lives in `~/Downloads/Downloads-organizer/`. Since the script only processes loose files at the top level of `~/Downloads` (and this folder is a subfolder), it will never move or alter its own files.

## Installing Dependencies

The only dependency is `watchdog`.

- Using pacman (recommended on Arch):
  ```
  sudo pacman -S python-watchdog
  ```
- Using pip:
  ```
  pip install --user -r requirements.txt
  ```

## Configuration (Optional)

Everything works out of the box with default values embedded in the script. To customize:

```
mkdir -p ~/.config/downloads-organizer
cp config.json.example ~/.config/downloads-organizer/config.json
```

JSON options:

| Key                 | Description                                           | Default        |
|---------------------|-------------------------------------------------------|----------------|
| `downloads_dir`     | Folder to monitor                                     | `~/Downloads`  |
| `delay_seconds`     | Wait time after the last change before moving         | `300`          |
| `sample_interval`   | Seconds between the two size measurements             | `3`            |
| `max_retries`       | Retries if the file size keeps changing               | `5`            |
| `extensions`        | Category → extension mapping (key = folder name)     | (listed)       |
| `other_category`    | Folder for unlisted extensions                        | `Otros`        |
| `ignore_extensions` | Extensions that are never moved (in-progress downloads) | `.part`, `.crdownload`, `.tmp` |

Extensions are compared case-insensitively. `config.json` does not support comments; use `config.json.example` as a template.

## Running Manually

```
python3 organizer.py
python3 organizer.py --delay 10 --quiet      # suppress console output
```

CLI options: `--config PATH`, `--delay SECONDS`, `--quiet`.

## systemd Service (Background Service)

```
cp downloads-organizer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now downloads-organizer.service
```

- Status: `systemctl --user status downloads-organizer.service`
- Live logs: `journalctl --user -u downloads-organizer.service -f`
- Dedicated (rotating) log: `~/.local/share/downloads-organizer/organizer.log`
- Disable: `systemctl --user disable --now downloads-organizer.service`

The service starts on login and automatically restarts if it fails.

## Behavior

- Only loose files in the top level of `~/Downloads` are organized (subfolders, including category folders, are ignored).
- Hidden files (`.`), extensions listed in `ignore_extensions`, and category folders are ignored (preventing loops).
- Collisions: instead of overwriting existing files, it appends a number like `file(1).txt`, `file(2).txt`, etc.
- If a file disappears before being moved, or if permission/IO errors occur, the event is logged and the service continues running.