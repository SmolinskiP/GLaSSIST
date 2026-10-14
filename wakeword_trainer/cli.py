"""Command line for the heavy training steps. Prints one JSON object per line so the wizard
(or any script) can follow the progress.

  python -m wakeword_trainer.cli init      --workspace DIR --word Bruninha --language pt
  python -m wakeword_trainer.cli download-models
  python -m wakeword_trainer.cli generate  --workspace DIR
  python -m wakeword_trainer.cli train     --workspace DIR [--epochs 40] [--rebuild]
  python -m wakeword_trainer.cli evaluate  --workspace DIR
  python -m wakeword_trainer.cli scan      --workspace DIR [--tag env] [--all-clips]
  python -m wakeword_trainer.cli info      --workspace DIR
"""
import argparse
import asyncio
import json
import sys


def emit(event, **data):
    print(json.dumps({'event': event, **data}, ensure_ascii=False), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='wakeword_trainer')
    ap.add_argument('command', choices=['init', 'download-models', 'generate', 'train', 'evaluate', 'scan', 'info'])
    ap.add_argument('--tag', default='env', help='scan: clip tag to scan (recorded everyday audio)')
    ap.add_argument('--all-clips', action='store_true', help='scan: include the clips used for training')
    ap.add_argument('--workspace')
    ap.add_argument('--word')
    ap.add_argument('--language', default='en')
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--rebuild', action='store_true')
    args = ap.parse_args(argv)
    log = lambda msg: emit('log', msg=msg)

    try:
        from .languages import load_corpus
        from .workspace import Project, Workspace
        if args.command == 'download-models':
            import openwakeword
            emit('step', name='download-models')
            openwakeword.utils.download_models()
            emit('result', ok=True)
            return 0
        if not args.workspace:
            ap.error('--workspace is required')
        if args.command == 'init':
            if not args.word:
                ap.error('--word is required for init')
            ws = Workspace(args.workspace, Project(word=args.word, language=args.language))
            ws.save_project()
            emit('result', **ws.summary(), model_name=ws.project.model_name)
            return 0
        ws = Workspace(args.workspace)
        emit('step', name=args.command)
        progress = lambda done, total: emit('progress', done=done, total=total)
        if args.command == 'info':
            emit('result', **ws.summary(), word=ws.project.word, model_name=ws.project.model_name)
        elif args.command == 'generate':
            from . import tts_gen
            stats = asyncio.run(tts_gen.generate(ws, load_corpus(ws.project.language), progress))
            emit('result', **stats)
        elif args.command == 'train':
            from . import train
            emit('result', **train.train(ws, args.epochs, progress=progress, log=log, rebuild=args.rebuild,
                                         stage=lambda name, state: emit('stage', name=name, state=state)))
        elif args.command == 'scan':
            from . import evaluate
            emit('result', **evaluate.scan_clips(ws, tag=args.tag, holdout_only=not args.all_clips,
                                                 progress=progress))
        elif args.command == 'evaluate':
            from . import evaluate
            emit('stage', name='evaluate', state='start')
            result = evaluate.evaluate(ws, progress=progress)
            emit('stage', name='evaluate', state='done')
            emit('result', **result)
        return 0
    except Exception as exc:  # report instead of a bare traceback; the wizard shows this text
        emit('error', msg=f'{type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
