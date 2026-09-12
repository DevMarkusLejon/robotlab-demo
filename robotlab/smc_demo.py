"""SMC-oriented placement/game runner. Offline by default, no ROS required."""
import argparse
import importlib
import json
from pathlib import Path
import uuid

from .placement_service import PlacementService
from .smc_workcell import Workcell
from .telemetry import TelemetryRecorder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--backend', choices=('offline', 'smc'), default='offline')
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--factory', help='Lab-owned module:function returning an SMCRobot')
    parser.add_argument('--execute', action='store_true', help='Enable configured physical execution')
    parser.add_argument('--camera-calibration', type=Path)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--cell', type=int, choices=range(9))
    parser.add_argument('--game', action='store_true', help='Offline automatic game; hardware terminal input')
    parser.add_argument('--fault', choices=('grasp', 'camera', 'motion', 'wrong_cell'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    robot = camera = None
    try:
        workcell = Workcell.load(args.config)
        if args.backend == 'smc':
            workcell.require_hardware()
        if args.check_config:
            print(json.dumps({'config_valid': True, 'backend': args.backend,
                              'hardware_verified': False}))
            return 0
        if args.game == (args.cell is not None):
            raise ValueError('choose_exactly_one_of_game_or_cell')
        output = args.output or Path('artifacts') / f'smc-{uuid.uuid4().hex}.jsonl'
        recorder = TelemetryRecorder(output)
        if args.backend == 'offline':
            from .smc_offline import OfflineRobot, OfflineCamera
            robot = OfflineRobot(workcell, args.fault)
            camera = OfflineCamera(robot)
        else:
            if not args.execute or not args.factory or not args.camera_calibration or args.fault:
                raise ValueError('physical_run_requires_execute_factory_camera_and_no_fault_injection')
            from .smc_adapter import SMCRobot
            from .smc_camera import PhysicalBoardCamera
            from .calibration import BoardCalibration
            # Camera must work with an empty board BEFORE a lab factory connects.
            camera = PhysicalBoardCamera(BoardCalibration.from_json(args.camera_calibration), args.camera)
            baseline = camera.observe(workcell.data['camera_timeout_s'])
            if not baseline.valid or any(baseline.cells):
                raise RuntimeError('initial_board_must_be_visible_and_empty')
            module, name = args.factory.split(':')
            robot = getattr(importlib.import_module(module), name)(workcell)
            if not isinstance(robot, SMCRobot):
                raise TypeError('lab_factory_must_return_SMCRobot')
        service = PlacementService(robot, camera, workcell, recorder)
        recorder.record('session_started', session_id=service.session_id,
                        source=camera.source, backend=args.backend)
        from .game import choose_move
        while True:
            board = service.match.board
            if not args.game:
                cell = args.cell
            elif args.backend == 'offline' or board.next_player == 'O':
                cell = choose_move(board)
            else:
                print('Bräde:', board.cells)
                cell = int(input('Välj tom ruta 0–8 (Ctrl+C avslutar): '))
            result = service.place(session_id=service.session_id,
                command_id=uuid.uuid4().hex, expected_revision=service.revision, cell=cell)
            print(json.dumps(result, ensure_ascii=False))
            if not args.game or service.match.board.winner or service.match.board.is_draw:
                break
        print(json.dumps({'completed': True, 'placements': service.revision,
            'source': camera.source, 'log': str(output),
            'physical_placements_in_this_run': service.revision if args.backend == 'smc' else 0}))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({'completed': False, 'error': str(error) or 'interrupted'}))
        return 1
    finally:
        try:
            if robot is not None:
                # A failed stop is an error, never a successful exit.
                robot.stop()
        finally:
            if camera is not None:
                camera.close()
            disconnect = getattr(robot, 'disconnect_gripper', None)
            if disconnect is not None:
                disconnect()


if __name__ == '__main__':
    raise SystemExit(main())
