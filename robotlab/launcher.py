"""Double-click Windows launcher for the installed WSL simulation."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
DISTRO = 'Ubuntu-22.04'
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def status():
    with urlopen('http://127.0.0.1:8766/status', timeout=1) as response:
        return json.load(response)


def wsl_path(path):
    return subprocess.check_output(
        ['wsl', '-d', DISTRO, '--exec', 'wslpath', '-a', path.as_posix()],
        creationflags=HIDDEN, encoding='utf-8').strip()


class Launcher:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title('RobotLab')
        self.window.geometry('650x395')
        self.window.resizable(False, False)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.closing = False
        self.restart_mode = None
        tk.Label(self.window, text='RobotLab', font=('Segoe UI', 25, 'bold')).pack(pady=(18, 5))
        tk.Label(self.window, text='Spela tre-i-rad med den simulerade roboten.',
                 font=('Segoe UI', 11)).pack()
        self.message = tk.StringVar(value='Startar…')
        tk.Label(self.window, textvariable=self.message, wraplength=540,
                 font=('Segoe UI', 11), height=4).pack(pady=8)
        self.button = tk.Button(self.window, text='Nytt spel', command=lambda: self.restart('game'),
                                font=('Segoe UI', 11), width=22)
        self.button.pack()
        tk.Button(self.window, text='Testa pekning utan robotrörelse', command=lambda: self.restart('hand')).pack(pady=5)
        tk.Button(self.window, text='Avsluta försöket', command=self.stop.set).pack()
        tk.Label(self.window, text='Nytt spel avbryter försöket och återställer hela scenen.', font=('Segoe UI', 9)).pack(pady=4)
        tk.Button(self.window, text='Öppna loggar', command=lambda: os.startfile(ROOT / 'artifacts')).pack(pady=8)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.after(100, self.poll)
        self.start()

    def restart(self, mode):
        if self.running:
            self.restart_mode = mode
            self.stop.set()
            self.message.set('Avslutar försöket och förbereder nästa…')
        else:
            self.start(mode)

    def start(self, mode='game'):
        if self.running:
            return
        self.running = True
        self.stop.clear()
        self.button.config(state='disabled')
        self.message.set('Startar pekningstestet…' if mode == 'hand' else
                         'Startar simulatorn. Första starten kan ta några minuter…')
        threading.Thread(target=self.run_session, kwargs={'hand_only': mode == 'hand'}, daemon=True).start()

    def run_session(self, check_only=False, hand_only=False):
        backend = camera = None
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        token = uuid.uuid4().hex
        stop_file = artifacts / ('desktop-' + token + '.stop')
        log_path = artifacts / ('desktop-' + token + '.log')
        try:
            try:
                status()
            except (OSError, ValueError):
                pass
            else:
                raise RuntimeError('En RobotLab-session körs redan. Stäng den innan du startar en ny.')
            with log_path.open('w', encoding='utf-8') as log:
                probe = subprocess.run([sys.executable, '-c',
                    'import PIL; from robotlab.webcam import HandTracker; t = HandTracker(); t.close()'],
                    cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN)
                if probe.returncode:
                    raise RuntimeError('Kamerans Python-paket eller handmodell kunde inte laddas. Se loggen.')
                if self.stop.is_set():
                    return
                if hand_only:
                    self.events.put(('ready', 'Testa att pekningen väljer rätt ruta och nollställs när handen tas bort. Inga robotkommandon skickas.'))
                    camera = subprocess.Popen([sys.executable, '-m', 'robotlab.webcam_robot', '--check-hand'],
                        cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN)
                    while camera.poll() is None and not self.stop.wait(0.5):
                        pass
                    if camera.poll() not in (None, 0):
                        raise RuntimeError('Pekningstestet misslyckades. Kontrollera kameran. Se loggen.')
                    return
                script = wsl_path(ROOT / 'simulation/ros2_ws/scripts/desktop_session.sh')
                backend = subprocess.Popen(['wsl', '-d', DISTRO, '--exec', 'bash', script,
                    wsl_path(stop_file)], cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN)
                deadline = time.monotonic() + 180
                while not self.stop.is_set():
                    if backend.poll() is not None:
                        raise RuntimeError('Simulatorn kunde inte starta. Se loggen för detaljer.')
                    try:
                        ready = status().get('mode') == 'game'
                        with urlopen('http://127.0.0.1:8766/camera.jpg', timeout=1) as frame:
                            ready = ready and frame.status == 200
                        if ready:
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError('Simulatorn eller brädkameran blev inte klar inom tre minuter.')
                    self.stop.wait(0.5)
                if self.stop.is_set() or check_only:
                    return
                self.events.put(('ready', 'Peka på en tom ruta och håll kvar cirka 1,2 sekunder. Roboten spelar sedan sitt motdrag.'))
                camera = subprocess.Popen([sys.executable, '-m', 'robotlab.webcam_robot'],
                    cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN)
                while camera.poll() is None and not self.stop.wait(0.5):
                    if backend.poll() is not None:
                        raise RuntimeError('Simulatorn avslutades oväntat. Se loggen.')
                    try:
                        self.events.put(('message', status()['message']))
                    except (OSError, ValueError):
                        self.events.put(('message', 'Kontakten med simulatorn saknas…'))
                if camera.poll() not in (None, 0):
                    raise RuntimeError('Kamerafönstret kunde inte köras. Kontrollera att kameran är ansluten och ledig. Se loggen.')
        except Exception as error:
            self.events.put(('error', str(error) + '\n\nLogg: ' + str(log_path)))
        finally:
            if camera is not None and camera.poll() is None:
                camera.terminate()
                camera.wait(timeout=10)
            if backend is not None and backend.poll() is None:
                self.events.put(('message', 'Stänger simulatorn…'))
                stop_file.touch()
                # The Linux wrapper stops only the processes owned by this session.
                backend.wait()
            stop_file.unlink(missing_ok=True)
            self.events.put(('done', 'Försöket är avslutat. Välj Nytt spel eller Testa pekning.'))

    def close(self):
        self.closing = True
        self.stop.set()
        self.message.set('Stänger kameran och simulatorn…')
        if not self.running:
            self.window.destroy()

    def poll(self):
        while not self.events.empty():
            kind, text = self.events.get_nowait()
            if kind == 'error':
                messagebox.showerror('RobotLab kunde inte köras', text, parent=self.window)
            elif kind == 'done':
                self.running = False
                self.button.config(state='normal')
                if self.closing:
                    self.window.destroy()
                    return
                if self.restart_mode:
                    mode, self.restart_mode = self.restart_mode, None
                    self.start(mode)
                    continue
                self.message.set(text)
            else:
                if kind == 'ready':
                    self.button.config(state='normal')
                self.message.set(text)
        self.window.after(100, self.poll)


def main():
    import msvcrt
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    with (ROOT / 'artifacts/desktop.lock').open('a+b') as lock:
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            window = tk.Tk()
            window.withdraw()
            messagebox.showinfo('RobotLab', 'RobotLab är redan öppet.', parent=window)
            window.destroy()
            return
        try:
            Launcher().window.mainloop()
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    main()
