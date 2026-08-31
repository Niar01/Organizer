#!/usr/bin/env python3
"""Organizador automático de ~/Downloads por tipo de archivo.

Vigila la carpeta de descargas con watchdog, espera a que cada descarga
termine (debounce + verificación de tamaño estable) y mueve el archivo a
una subcarpeta según su extensión.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

DEFAULT_CONFIG = {
    "downloads_dir": "~/Downloads",
    "delay_seconds": 300,      # segundos de espera tras el último cambio del archivo
    "sample_interval": 3,      # segundos entre las dos mediciones de tamaño
    "max_retries": 5,          # reintentos si el tamaño sigue cambiando
    "extensions": {
        "Documentos": [".txt", ".pdf", ".doc", ".docx", ".odt", ".md"],
        "Hojas de calculo": [".xls", ".xlsx", ".csv", ".ods"],
        "Comprimidos": [".tar", ".tar.gz", ".zip", ".rar", ".7z", ".gz", ".xz"],
        "Imagenes": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp"],
        "Audio": [".mp3", ".wav", ".flac", ".ogg"],
        "Video": [".mp4", ".mkv", ".avi", ".mov", ".webm"],
        "Ejecutables y paquetes": [".AppImage", ".deb", ".rpm", ".pkg.tar.zst"],
    },
    "other_category": "Otros",
    "ignore_extensions": [".part", ".crdownload", ".tmp"],
}

DEFAULT_CONFIG_PATH = Path.home() / ".config" / \
    "downloads-organizer" / "config.json"
LOG_DIR = Path.home() / ".local" / "share" / "downloads-organizer"
LOG_FILE = LOG_DIR / "organizer.log"


def setup_logging(quiet=False):
    """Configura el log en archivo (rotativo) y en consola."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("downloads-organizer")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if not quiet:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

    return logger


def load_config(logger, custom_path=None):
    """Carga la configuración JSON externa, completándola con los valores por defecto."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    path = Path(custom_path) if custom_path else DEFAULT_CONFIG_PATH
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key in (
                "downloads_dir",
                "delay_seconds",
                "sample_interval",
                "max_retries",
                "extensions",
                "other_category",
                "ignore_extensions",
            ):
                if key in data:
                    config[key] = data[key]
        except (json.JSONDecodeError, OSError) as err:
            logger.error(
                "No se pudo leer %s (%s); se usan los valores por defecto.", path, err
            )
    config["extensions"] = {
        cat: [ext.lower() for ext in exts] for cat, exts in config["extensions"].items()
    }
    config["ignore_extensions"] = [ext.lower()
                                   for ext in config["ignore_extensions"]]
    return config


class DownloadsOrganizer:
    def __init__(self, config, logger):
        self.logger = logger
        self.downloads_dir = Path(os.path.expanduser(
            config["downloads_dir"])).resolve()
        self.delay = max(0, int(config["delay_seconds"]))
        self.sample_interval = max(0, int(config["sample_interval"]))
        self.max_retries = max(1, int(config.get("max_retries", 5)))
        self.other_category = str(config.get("other_category", "Otros"))
        self.ignore_extensions = sorted(
            config.get("ignore_extensions", []), key=len, reverse=True
        )

        # extensiones ordenadas de mayor a menor longitud para capturar
        # sufijos compuestos como ".tar.gz" o ".pkg.tar.zst" antes que ".gz"
        self.flat_extensions = sorted(
            ((ext, cat)
             for cat, exts in config["extensions"].items() for ext in exts),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.category_dirs = {
            cat: self.downloads_dir / cat for cat in config["extensions"]
        }
        self.category_dirs[self.other_category] = self.downloads_dir / \
            self.other_category

        self.pending = {}
        self.retries = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

    def start(self):
        """Crea las carpetas de categoría y arranca el hilo de trabajo."""
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        for category, folder in self.category_dirs.items():
            folder.mkdir(parents=True, exist_ok=True)
            self.logger.info("Carpeta de categoría lista: %s", folder)

        threading.Thread(
            target=self._worker, name="downloads-organizer-worker", daemon=True
        ).start()
        try:
            for entry in self.downloads_dir.iterdir():
                if entry.is_file() and self._should_process(str(entry)):
                    self.enqueue(str(entry))
        except OSError as err:
            self.logger.error(
                "No se pudo revisar los archivos existentes: %s", err)

    def enqueue(self, path):
        """Registra (o refresca) un archivo pendiente de organizar."""
        with self.lock:
            self.pending[path] = time.time()
            self.retries.pop(path, None)
        self.logger.info(
            "Detectado: %s (se organizará en %ds)", path, self.delay)

    def handle_path(self, path):
        """Procesa un evento de watchdog: solo archivos sueltos en ~/Downloads."""
        try:
            parent = Path(path).parent.resolve()
        except OSError:
            return
        if parent != self.downloads_dir:
            return
        if self._should_process(path):
            self.enqueue(path)

    def _should_process(self, path):
        name = os.path.basename(path)
        if name.startswith("."):
            return False
        lower = name.lower()
        return not any(lower.endswith(ext) for ext in self.ignore_extensions)

    def _category_of(self, name):
        lower = name.lower()
        for ext, category in self.flat_extensions:
            if lower.endswith(ext):
                return category
        return self.other_category

    def _worker(self):
        """Bucle principal: mueve los archivos cuyo debounce ya venció."""
        while not self.stop_event.is_set():
            now = time.time()
            due = []
            with self.lock:
                for path, last_event in list(self.pending.items()):
                    if now - last_event >= self.delay:
                        due.append(path)
            for path in due:
                with self.lock:
                    self.pending.pop(path, None)
                self._process(path)
            self.stop_event.wait(1.0)

    def _process(self, path):
        try:
            if not os.path.isfile(path):
                self.logger.info(
                    "Ya no existe (borrado o movido por el usuario): %s", path)
                return
            if Path(path).parent.resolve() in {
                folder.resolve() for folder in self.category_dirs.values()
            }:
                return
            if not self._size_is_stable(path):
                attempts = self.retries.get(path, 0) + 1
                if attempts >= self.max_retries:
                    self.logger.warning(
                        "El archivo sigue cambiando de tamaño tras %d intentos; se deja en su lugar: %s",
                        attempts,
                        path,
                    )
                    return
                self.retries[path] = attempts
                self.logger.info(
                    "El archivo aún parece en descarga, se reintentará: %s", path)
                with self.lock:
                    self.pending[path] = time.time()
                return

            name = os.path.basename(path)
            destination = self.category_dirs[self._category_of(name)]
            destination.mkdir(parents=True, exist_ok=True)
            target = self._unique_target(destination, name)
            shutil.move(path, str(target))
            self.logger.info("Movido: %s -> %s", path, target)
        except FileNotFoundError:
            self.logger.info(
                "El archivo desapareció antes de moverse: %s", path)
        except PermissionError as err:
            self.logger.error(
                "Permiso denegado al organizar %s: %s", path, err)
        except (OSError, shutil.Error) as err:
            self.logger.error("Error al organizar %s: %s", path, err)

    def _size_is_stable(self, path):
        """Compara el tamaño del archivo antes y después de un intervalo corto."""
        try:
            first = os.path.getsize(path)
            if self.sample_interval:
                time.sleep(self.sample_interval)
            second = os.path.getsize(path)
        except OSError:
            return False
        return first == second

    @staticmethod
    def _unique_target(destination, name):
        """Devuelve un nombre de destino que no colisione: archivo(1).txt, etc."""
        target = destination / name
        if not target.exists():
            return target
        stem, suffix = os.path.splitext(name)
        counter = 1
        while True:
            candidate = destination / f"{stem}({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1


class DownloadsHandler(FileSystemEventHandler):
    def __init__(self, organizer):
        super().__init__()
        self.organizer = organizer

    def on_created(self, event):
        self.organizer.handle_path(event.src_path)

    def on_modified(self, event):
        self.organizer.handle_path(event.src_path)

    def on_moved(self, event):
        self.organizer.handle_path(event.dest_path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Organiza automáticamente los archivos de ~/Downloads por tipo."
    )
    parser.add_argument(
        "--config",
        metavar="RUTA",
        help="Archivo JSON de configuración (por defecto: ~/.config/downloads-organizer/config.json)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        metavar="SEGUNDOS",
        help="Sobrescribe el tiempo de espera antes de mover archivos",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="No imprimir mensajes por consola"
    )
    args = parser.parse_args(argv)

    logger = setup_logging(quiet=args.quiet)
    config = load_config(logger, args.config)
    if args.delay is not None and args.delay >= 0:
        config["delay_seconds"] = args.delay

    organizer = DownloadsOrganizer(config, logger)
    observer = Observer()
    observer.schedule(
        DownloadsHandler(organizer), str(organizer.downloads_dir), recursive=False
    )
    organizer.start()
    observer.start()
    logger.info(
        "Organizador activo. Vigilando %s (espera: %ds).",
        organizer.downloads_dir,
        organizer.delay,
    )

    try:
        while not organizer.stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Detenido por el usuario (Ctrl+C).")
    finally:
        organizer.stop_event.set()
        observer.stop()
        observer.join()
        logger.info("Organizador detenido.")


if __name__ == "__main__":
    main()
