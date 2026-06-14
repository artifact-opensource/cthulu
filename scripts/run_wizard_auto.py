import traceback
try:
    import config.wizard as w
    # Auto-accept defaults
    w.get_input = lambda prompt, default='': default
    cfg = w.run_setup_wizard('config.json')
    print('\n--- WIZARD RUN COMPLETE ---')
    if cfg is None:
        print('Wizard returned None')
    else:
        print('Config keys:', list(cfg.keys()))
        import pathlib
        p = pathlib.Path('config.json')
        print('config.json exists?', p.exists())
        if p.exists():
            print('Size', p.stat().st_size)
            print('\nPreview:\n' + p.read_text()[:400])
except Exception:
    traceback.print_exc()
