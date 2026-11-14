{{#if rest_note}}
- {{rest_note}}
{{/if}}
{{#unless allow_camera}}
- カメラ（take_snapshot）は今は使わないこと。
{{/unless}}
{{#unless allow_speak}}
- 声（speak）は今は出さないこと。伝えたいことは、ボイスメモ（save_tts_memo。音は出ない）に残してよい。
{{/unless}}
{{#if allow_speak}}
- 体が眠っているあいだに speak した声は、体が起きたときに出る（残るのは最後の 1 つ）。いま声を出したいときは、先に wake で自分で起きてよい。
{{/if}}
{{#unless allow_sound}}
- 音（play_sound, play_icon）は今は出さないこと。
{{/unless}}
{{#unless allow_mic}}
- マイク（mic_start）は今は使わないこと。
{{/unless}}
