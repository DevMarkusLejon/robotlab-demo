"""Native desktop game for the SMC offline contract. Never connects to hardware."""
import argparse
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
import uuid

from .game import choose_move
from .placement_service import PlacementService
from .smc_offline import OfflineCamera, OfflineRobot
from .smc_workcell import Workcell
from .telemetry import TelemetryRecorder

ROOT = Path(__file__).resolve().parents[1]
BG, PANEL, INK, MUTED = '#101827', '#1b293e', '#edf3ff', '#9baec8'


class OfflineApp:
    def __init__(self, window):
        self.window = window
        window.title('RobotLab | SMC offline')
        window.geometry('1060x730+80+50')
        window.configure(bg=BG)
        window.minsize(960, 700)
        self.events = queue.Queue()
        self.busy = False
        self.automatic = False
        self.pending = None
        self.closing = False
        self.fault = tk.StringVar(value='none')
        self.heading = tk.StringVar()
        self.details = tk.StringVar()
        self.session = tk.StringVar()

        def label(parent, text='', size=11, color=INK, **kw):
            return tk.Label(parent, text=text, font=('Segoe UI', size),
                            bg=parent['bg'], fg=color, **kw)

        header = tk.Frame(window, bg=BG)
        header.pack(fill='x', padx=30, pady=(22, 12))
        label(header, 'ROBOTLAB / SMC', 24).pack(anchor='w')
        label(header, 'OFFLINE-KONTRAKT  •  Körs lokalt på den här datorn', 12,
              '#66dbc1').pack(anchor='w', pady=(5, 0))
        label(header, 'Syntetiska observationer. Ingen fysisk robot, kamera eller 5G.',
              color=MUTED).pack(anchor='w', pady=(4, 0))
        content = tk.Frame(window, bg=BG)
        content.pack(fill='both', expand=True, padx=30)
        left = tk.Frame(content, bg=PANEL, padx=16, pady=14)
        left.pack(side='left', fill='both', expand=True, padx=(0, 16))
        label(left, size=19, textvariable=self.heading).pack(anchor='w')
        label(left, text='Du spelar X · robotmotståndaren spelar O', color=MUTED).pack(anchor='w', pady=(4, 12))
        grid = tk.Frame(left, bg=PANEL)
        grid.pack(fill='both', expand=True)
        self.cells = []
        for i in range(9):
            grid.rowconfigure(i // 3, weight=1)
            grid.columnconfigure(i % 3, weight=1)
            button = tk.Button(grid, text=str(i + 1), font=('Segoe UI', 31, 'bold'),
                bg='#263951', fg=MUTED, disabledforeground=INK,
                activebackground='#395372', activeforeground=INK, relief='flat',
                bd=0, command=lambda cell=i: self.place(cell))
            button.grid(row=i // 3, column=i % 3, sticky='nsew', padx=4, pady=4)
            self.cells.append(button)
        right = tk.Frame(content, bg=PANEL, padx=18, pady=14, width=390)
        right.pack(side='right', fill='both')
        right.pack_propagate(False)
        label(right, 'Placering & kvittens', 18).pack(anchor='w')
        label(right, textvariable=self.details, justify='left', anchor='nw',
              wraplength=350, height=5).pack(fill='x', pady=(12, 8))
        label(right, 'Händelser från PlacementService', color=MUTED).pack(anchor='w')
        self.log = tk.Text(right, bg=BG, fg=INK, font=('Consolas', 10),
                           relief='flat', wrap='word', state='disabled', height=12)
        self.log.pack(fill='both', expand=True, pady=8)
        label(right, 'Felprov för nästa placering', color=MUTED).pack(anchor='w')
        self.fault_menu = tk.OptionMenu(right, self.fault, 'none', 'grasp', 'camera', 'motion', 'wrong_cell')
        self.fault_menu.configure(bg='#263951', fg=INK, relief='flat', highlightthickness=0)
        self.fault_menu.pack(fill='x', pady=(4, 0))
        footer = tk.Frame(window, bg=BG)
        footer.pack(fill='x', padx=30, pady=16)
        self.controls = []
        for text, callback in [('Nytt spel', self.reset), ('Kör automatiskt', self.autoplay),
                               ('Öppna loggar', self.open_logs)]:
            button = tk.Button(footer, text=text, command=callback, bg='#263951',
                fg=INK, relief='flat', padx=18, pady=10, font=('Segoe UI', 11))
            button.pack(side='left', padx=(0, 10))
            self.controls.append(button)
        label(window, textvariable=self.session, color=MUTED).pack(anchor='w', padx=30, pady=(0, 15))
        window.protocol('WM_DELETE_WINDOW', self.close)
        self.reset()
        window.after(30, self.poll)

    def append(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def reset(self):
        if self.busy:
            return
        if self.pending:
            self.window.after_cancel(self.pending)
            self.pending = None
        self.automatic = False
        self.fault.set('none')
        workcell = Workcell.load(ROOT / 'config/smc-offline.json')
        self.robot = OfflineRobot(workcell)
        self.camera = OfflineCamera(self.robot)
        self.recorder = TelemetryRecorder(ROOT / 'artifacts' / f'smc-ui-{uuid.uuid4().hex}.jsonl')
        self.service = PlacementService(self.robot, self.camera, workcell, self.recorder)
        self.recorder.record('session_started', session_id=self.service.session_id,
                             source=self.camera.source, backend='offline', frontend='desktop')
        self.session.set(f'Session {self.service.session_id[:12]}  |  Logg: {self.recorder.path.name}')
        self.details.set('0 / 9 placeringar\nTre färska fixture-observationer krävs per drag.\nFysiska placeringar: 0')
        self.append('Ny offline-session. Välj en tom ruta.')
        self.refresh()

    def refresh(self):
        board = self.service.match.board
        terminal = board.is_draw or board.winner
        self.heading.set('Stoppad efter fel' if self.service.failed else
            'Oavgjort — spelet klart' if board.is_draw else
            f'{board.winner} vann' if board.winner else
            'Placering pågår…' if self.busy else
            'Din tur' if board.next_player == 'X' else 'Robotens tur')
        for i, button in enumerate(self.cells):
            token = board.cells[i]
            color = '#ff8585' if token == 'X' else '#7daeff' if token == 'O' else MUTED
            enabled = not (self.busy or self.automatic or self.service.failed or terminal or token
                           or board.next_player != 'X' or self.pending)
            button.configure(text=token or str(i + 1), fg=color, disabledforeground=color,
                             state='normal' if enabled else 'disabled')
        self.controls[0].configure(state='disabled' if self.busy else 'normal')
        self.controls[1].configure(state='disabled' if self.busy or terminal or self.service.failed
                                  or self.pending or self.automatic else 'normal')
        self.fault_menu.configure(state='disabled' if self.busy or self.pending else 'normal')

    def autoplay(self):
        if self.busy or self.service.failed or self.pending:
            return
        self.automatic = True
        self.place(choose_move(self.service.match.board))

    def place(self, cell):
        self.pending = None
        if self.busy or self.service.failed or self.closing:
            return
        self.busy = True
        self.robot.fault = None if self.fault.get() == 'none' else self.fault.get()
        self.details.set(f'Ruta {cell + 1}: hämtning → placering → verifiering\nKälla: offline_fixture\nFysiska placeringar: 0')
        self.refresh()
        service = self.service
        def work():
            try:
                result = service.place(session_id=service.session_id, command_id=uuid.uuid4().hex,
                                       expected_revision=service.revision, cell=cell)
                self.events.put(('ok', result))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        if self.closing:
            return
        try:
            kind, result = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if kind == 'error':
                self.automatic = False
                self.details.set(f'Placeringen avvisades. Brädet ändrades inte.\n{result}\nStarta ett nytt offline-spel för att återställa.')
                self.append(f'AVVISAT: {result}\nStopp anropat: {self.robot.stops} gång(er).')
            else:
                self.details.set(f'{result["revision"]} / 9 placeringar\n3 färska fixture-observationer godkända.\nFysiska placeringar: 0')
                self.append(f'Drag {result["revision"]} bekräftat\n  frame …{result["frame_id"][-10:]}\n  attempt {result["attempt_id"][:10]}')
                board = self.service.match.board
                if not (board.winner or board.is_draw) and (self.automatic or board.next_player == 'O'):
                    self.pending = self.window.after(650, lambda: self.place(choose_move(self.service.match.board)))
            self.refresh()
        self.window.after(30, self.poll)

    def open_logs(self):
        if os.name == 'nt':
            os.startfile(self.recorder.path.parent)

    def close(self):
        self.closing = True
        if self.pending:
            self.window.after_cancel(self.pending)
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--autoplay', action='store_true')
    args = parser.parse_args()
    window = tk.Tk()
    app = OfflineApp(window)
    if args.autoplay:
        window.after(500, app.autoplay)
    window.mainloop()


if __name__ == '__main__':
    main()
