# Natural‑Language Media Prompts (Audio + Video)

These examples work in:
- `Audio Editor` prompt bar (top)
- `Video Editor` prompt bar (top)
- `File Tools → AI Assist` (when the tool exists for the request)

Tip: You can combine multiple instructions in one prompt (comma or “and then”).

## Audio examples

1. `grab track 16 - DtMF.flac and create a ringtone by cutting between 1:23 to 1:41 into DtMF_Ringtone.mp3`
2. `grab file 11 - TURiSTA.flac and cut it between 00:00:00 to 00:00:35.735 and starting from 00:00:25.000 start to fade out the audio until it ends and then exported as mp3`
3. `use "My Song.flac" trim 0:10-0:40, export mp3 320k as my_song_clip`
4. `cut 00:01:10 to 00:01:55, normalize, export mp3 192k`
5. `export as wav` (keeps current In/Out selection)
6. `volume -3, export mp3 320k`
7. `normalize and export opus 96k`
8. `fade out starting from 2:10 until it ends` (uses current Out / end of file)
9. `fade in 0.5s at the beginning, export mp3 256k`
10. `convert to m4a 160k and name it "Podcast_Clip"`

## Video examples

1. `grab clip 1 - intro.mp4 and cut between 0:10 to 0:25 and export as intro_cut.mp4 720p h265 30fps`
2. `cut 1:23-1:41, export mkv 1080p h264 crf 18`
3. `export mp4 720p h264 30fps gpu`
4. `export webm 1080p vp9 30fps`
5. `crf 22, export mp4`
6. `use gpu nvenc, export mp4 1080p h265`

## File Tools → AI Assist examples

1. `convert all audio in this folder to mp3 320kbps into folder named MP3 Music`
2. `cut 1:23 to 1:41 from DtMF.flac and export as DtMF_Ringtone.mp3`
3. `convert all images in this folder to webp into Converted_Images`
4. `zip folder into archive.7z`
5. `index this folder, then find invoices from Duke Energy`

