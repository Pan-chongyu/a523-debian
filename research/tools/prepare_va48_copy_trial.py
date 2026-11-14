"""Keep the same frozen v8 workload and pin only the diagnostic boot identity."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'firmware/run_guarded_copy_trial.py').read_text()
source=source.replace("'7.3.3-tzx-a523-accel1' and '#5 '","'7.3.3-tzx-a523-va48' and '#7 '")
source=source.replace('3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c',
                      'f4055eda1458b18800f99661ed625e081af477eb521b4ac7db0b79cada356b16')
source=source.replace('copy-readonly-v8-high','copy-va48-v8-high')
source=source.replace("for module in ('panfrost',", "for module in ('tzx_display', 'tzx_gsl3670', 'tzx_codec_driver', 'aic8800_fdrv', 'aic8800_bsp', 'panfrost',")
source=source.replace('GUARDED_COPY_TRIAL','VA48_GUARDED_COPY_TRIAL')
compile(source,'run_va48_copy_trial.py','exec')
target=root/'firmware/run_va48_copy_trial.py'
assert not target.exists()
target.write_text(source,encoding='utf8',newline='\n')
