{{#if rest_note}}
- {{rest_note}}
{{/if}}
{{#unless allow_camera}}
- カメラ（take_snapshot）は今は使わないこと。
{{/unless}}
{{#unless allow_speak}}
- 声（speak）は今は出さないこと。
{{/unless}}
{{#unless allow_sound}}
- 音（play_sound, play_icon）は今は出さないこと。
{{/unless}}
{{#unless allow_mic}}
- マイク（mic_start）は今は使わないこと。
{{/unless}}
