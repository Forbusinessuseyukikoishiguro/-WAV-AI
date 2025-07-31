#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
英語音声→日本語字幕生成ツール（WAV専用・FFmpeg不要版）
English Speech to Japanese Subtitle Generator (WAV Only)

WAVファイルのみ対応、FFmpegとpydub不要
"""

import os
import sys
from datetime import datetime, timedelta

# 必要なライブラリのインポートを安全に行う
try:
    import json
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    from openai import OpenAI
    import wave
    import configparser
    import re
    IMPORTS_OK = True
    MISSING_MODULE = ""
except ImportError as e:
    IMPORTS_OK = False
    MISSING_MODULE = str(e)

class EnglishToJapaneseSubtitle:
    def __init__(self, api_key=None):
        if not IMPORTS_OK:
            return
        self.client = None
        
        if api_key:
            self.set_api_key(api_key)
    
    def set_api_key(self, api_key):
        """OpenAI APIキーを設定"""
        try:
            self.client = OpenAI(api_key=api_key)
            # APIキーの有効性をテスト
            self.client.models.list()
            return True
        except Exception as e:
            print(f"APIキー設定エラー: {e}")
            self.client = None
            return False
    
    def validate_wav_file(self, wav_file):
        """WAVファイルの妥当性をチェック"""
        try:
            with wave.open(wav_file, 'rb') as wf:
                # ファイル情報を取得
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                frames = wf.getnframes()
                duration = frames / float(framerate)
                
                print(f"WAVファイル情報:")
                print(f"  チャンネル数: {channels}")
                print(f"  サンプル幅: {sample_width} bytes")
                print(f"  サンプルレート: {framerate} Hz")
                print(f"  長さ: {duration:.2f} 秒")
                
                # ファイルサイズチェック（25MB制限）
                file_size = os.path.getsize(wav_file)
                if file_size > 25 * 1024 * 1024:
                    return False, f"ファイルサイズが大きすぎます: {file_size / (1024*1024):.1f}MB（上限: 25MB）"
                
                return True, "WAVファイルは有効です"
                
        except Exception as e:
            return False, f"WAVファイルの読み込みエラー: {e}"
    
    def transcribe_english_with_timestamps(self, audio_file):
        """英語音声をタイムスタンプ付きで認識"""
        if self.client is None:
            return "OpenAI APIキーが設定されていません"
        
        # WAVファイルの妥当性チェック
        is_valid, message = self.validate_wav_file(audio_file)
        if not is_valid:
            return message
        
        try:
            with open(audio_file, "rb") as audio:
                # 新しいAPIバージョンと古いバージョンに対応
                try:
                    # 新しいAPI（timestamp_granularities対応）を試す
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio,
                        language="en",
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )
                except Exception as new_api_error:
                    # 古いAPI（timestamp_granularities未対応）にフォールバック
                    audio.seek(0)  # ファイルポインタをリセット
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio,
                        language="en",
                        response_format="verbose_json"
                    )
            
            # セグメント情報を含む結果を返す
            result = {
                'text': transcript.text,
                'language': transcript.language,
                'duration': transcript.duration,
                'segments': transcript.segments if hasattr(transcript, 'segments') else []
            }
            
            return result
        except Exception as e:
            return f"英語音声認識エラー: {e}"
    
    def translate_to_japanese(self, english_text, context="subtitle"):
        """英語テキストを日本語に翻訳"""
        if self.client is None:
            return "OpenAI APIキーが設定されていません"
        
        try:
            # 翻訳用プロンプト
            if context == "subtitle":
                system_prompt = """あなたは映像字幕の専門翻訳者です。以下の英語テキストを自然で読みやすい日本語字幕に翻訳してください。

翻訳の際の注意事項：
- 字幕として読みやすい自然な日本語にする
- 文脈を考慮し、映像に合う表現を使う
- 敬語は文脈に応じて適切に使用
- 専門用語は日本語で一般的な表現を使用
- 長すぎる文は適切に分割する
"""
            else:
                system_prompt = "以下の英語テキストを自然な日本語に翻訳してください。"
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": english_text}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"翻訳エラー: {e}"
    
    def create_subtitle_segments(self, transcription_result):
        """音声認識結果から字幕セグメントを作成"""
        if isinstance(transcription_result, str):
            return transcription_result
        
        segments = transcription_result.get('segments', [])
        if not segments:
            # セグメント情報がない場合は全体を翻訳
            english_text = transcription_result.get('text', '')
            japanese_text = self.translate_to_japanese(english_text)
            return [{
                'start': 0,
                'end': transcription_result.get('duration', 0),
                'english': english_text,
                'japanese': japanese_text
            }]
        
        subtitle_segments = []
        for segment in segments:
            english_text = segment.get('text', '').strip()
            if english_text:
                japanese_text = self.translate_to_japanese(english_text)
                subtitle_segments.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'english': english_text,
                    'japanese': japanese_text
                })
        
        return subtitle_segments
    
    def format_time_srt(self, seconds):
        """秒数をSRT形式のタイムスタンプに変換"""
        td = timedelta(seconds=seconds)
        hours = int(td.total_seconds() // 3600)
        minutes = int((td.total_seconds() % 3600) // 60)
        secs = int(td.total_seconds() % 60)
        millisecs = int((td.total_seconds() % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def generate_srt_content(self, subtitle_segments):
        """SRT形式の字幕コンテンツを生成"""
        srt_content = ""
        for i, segment in enumerate(subtitle_segments, 1):
            start_time = self.format_time_srt(segment['start'])
            end_time = self.format_time_srt(segment['end'])
            
            srt_content += f"{i}\n"
            srt_content += f"{start_time} --> {end_time}\n"
            srt_content += f"{segment['japanese']}\n\n"
        
        return srt_content
    
    def generate_bilingual_text(self, subtitle_segments):
        """英日対訳テキストを生成"""
        text_content = "=" * 60 + "\n"
        text_content += "英語音声 → 日本語字幕\n"
        text_content += f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        text_content += "=" * 60 + "\n\n"
        
        for i, segment in enumerate(subtitle_segments, 1):
            start_time = self.format_time_display(segment['start'])
            end_time = self.format_time_display(segment['end'])
            
            text_content += f"[{i:03d}] {start_time} - {end_time}\n"
            text_content += f"EN: {segment['english']}\n"
            text_content += f"JA: {segment['japanese']}\n"
            text_content += "-" * 40 + "\n\n"
        
        return text_content
    
    def format_time_display(self, seconds):
        """表示用のタイムスタンプフォーマット"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def process_wav_file(self, file_path, progress_callback=None):
        """WAVファイルを処理して字幕を生成"""
        try:
            if progress_callback:
                progress_callback("WAVファイルを確認中...")
            
            # WAVファイルの拡張子チェック
            if not file_path.lower().endswith('.wav'):
                return "WAVファイルのみ対応しています。他の形式は事前にWAVに変換してください。"
            
            if progress_callback:
                progress_callback("英語音声を認識中...")
            
            # 英語音声認識（タイムスタンプ付き）
            transcription_result = self.transcribe_english_with_timestamps(file_path)
            
            if isinstance(transcription_result, str):
                return transcription_result
            
            if progress_callback:
                progress_callback("日本語に翻訳中...")
            
            # 字幕セグメント作成（翻訳含む）
            subtitle_segments = self.create_subtitle_segments(transcription_result)
            
            if progress_callback:
                progress_callback("完了！")
            
            return {
                'segments': subtitle_segments,
                'original_text': transcription_result.get('text', ''),
                'duration': transcription_result.get('duration', 0)
            }
            
        except Exception as e:
            return f"処理エラー: {e}"

class SubtitleGeneratorGUI:
    def __init__(self):
        if not IMPORTS_OK:
            return
        self.config_manager = ConfigManager()
        self.subtitle_gen = EnglishToJapaneseSubtitle()
        self.current_segments = None
        self.setup_gui()
        self.load_saved_settings()
    
    def setup_gui(self):
        """GUIをセットアップ"""
        self.root = tk.Tk()
        self.root.title("英語音声→日本語字幕生成ツール（WAV専用）")
        self.root.geometry("1000x800")
        
        # メニュー
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # ファイルメニュー
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ファイル", menu=file_menu)
        file_menu.add_command(label="WAVファイルを開く", command=self.open_file)
        file_menu.add_separator()
        file_menu.add_command(label="SRT字幕を保存", command=self.save_srt)
        file_menu.add_command(label="対訳テキストを保存", command=self.save_bilingual_text)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.root.quit)
        
        # ツールメニュー
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ツール", menu=tools_menu)
        tools_menu.add_command(label="音声変換ツール情報", command=self.show_conversion_help)
        
        # 設定メニュー
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="設定", menu=settings_menu)
        settings_menu.add_command(label="API設定", command=self.show_api_settings)
        
        # メインフレーム
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # API設定フレーム
        api_frame = ttk.LabelFrame(main_frame, text="OpenAI API設定")
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(api_frame, text="APIキー:").pack(side=tk.LEFT, padx=5)
        self.api_key_var = tk.StringVar()
        api_entry = tk.Entry(api_frame, textvariable=self.api_key_var, show="*", width=40)
        api_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(api_frame, text="設定", command=self.set_api_key).pack(side=tk.LEFT, padx=5)
        self.api_status_label = tk.Label(api_frame, text="未設定", fg="red")
        self.api_status_label.pack(side=tk.LEFT, padx=5)
        
        # 操作ボタンフレーム
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(button_frame, text="🎵 WAVファイルを選択", 
                 command=self.open_file, width=20, bg="#4CAF50", fg="white", 
                 font=("", 12, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(button_frame, text="🔧 音声変換ヘルプ", 
                 command=self.show_conversion_help, width=15, bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(button_frame, text="🗑️ 結果をクリア", 
                 command=self.clear_result, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        # 保存ボタン
        save_frame = tk.Frame(button_frame)
        save_frame.pack(side=tk.RIGHT)
        tk.Button(save_frame, text="💾 SRT字幕保存", 
                 command=self.save_srt, width=12, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(save_frame, text="📄 対訳テキスト保存", 
                 command=self.save_bilingual_text, width=15, bg="#FF9800", fg="white").pack(side=tk.LEFT)
        
        # 注意書き
        note_frame = tk.Frame(main_frame)
        note_frame.pack(fill=tk.X, pady=(0, 10))
        note_label = tk.Label(note_frame, text="📌 このバージョンはWAVファイルのみ対応（FFmpeg不要・軽量版）", 
                             fg="blue", font=("", 10, "bold"))
        note_label.pack()
        
        # プログレスバー
        self.progress_var = tk.StringVar()
        self.progress_label = tk.Label(main_frame, textvariable=self.progress_var, fg="blue")
        self.progress_label.pack(fill=tk.X, pady=(0, 10))
        
        # タブ設定
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # 対訳表示タブ
        bilingual_frame = ttk.Frame(notebook)
        notebook.add(bilingual_frame, text="📖 英日対訳")
        
        self.bilingual_text = scrolledtext.ScrolledText(bilingual_frame, height=25, width=100, 
                                                       font=("", 11))
        self.bilingual_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # SRT字幕タブ
        srt_frame = ttk.Frame(notebook)
        notebook.add(srt_frame, text="🎬 SRT字幕")
        
        self.srt_text = scrolledtext.ScrolledText(srt_frame, height=25, width=100, 
                                                 font=("Courier", 10))
        self.srt_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 日本語のみタブ
        japanese_frame = ttk.Frame(notebook)
        notebook.add(japanese_frame, text="🗾 日本語字幕のみ")
        
        self.japanese_text = scrolledtext.ScrolledText(japanese_frame, height=25, width=100, 
                                                      font=("", 12))
        self.japanese_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ステータスバー
        self.status_var = tk.StringVar()
        self.status_var.set("OpenAI APIキーを設定してください")
        status_bar = tk.Label(self.root, textvariable=self.status_var, 
                             relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def show_conversion_help(self):
        """音声変換ヘルプを表示"""
        help_window = tk.Toplevel(self.root)
        help_window.title("音声ファイル変換方法")
        help_window.geometry("600x500")
        help_window.transient(self.root)
        
        help_text = """🔧 音声ファイル変換方法

このツールはWAVファイルのみ対応しています。
他の形式（MP3, M4A等）は事前にWAVに変換してください。

【無料変換ツール】

1️⃣ Audacity（推奨）
   • https://www.audacityteam.org/
   • インポート → エクスポート → WAV選択

2️⃣ VLC Media Player
   • メディア → 変換/保存
   • プロファイルでWAVを選択

3️⃣ オンライン変換サイト
   • https://convertio.co/ja/
   • https://online-audio-converter.com/ja/

4️⃣ Windows標準（PowerShell）
   以下のコマンドをコピーして実行：

---コマンド開始---
Add-Type -AssemblyName System.Windows.Forms
$openFileDialog = New-Object System.Windows.Forms.OpenFileDialog
$openFileDialog.Filter = "音声ファイル|*.mp3;*.m4a;*.flac;*.ogg"
$result = $openFileDialog.ShowDialog()
if ($result -eq "OK") {
    $inputFile = $openFileDialog.FileName
    $outputFile = [System.IO.Path]::GetDirectoryName($inputFile) + "\\" + [System.IO.Path]::GetFileNameWithoutExtension($inputFile) + ".wav"
    Write-Host "変換中: $inputFile → $outputFile"
    # ここでffmpegコマンドが必要
}
---コマンド終了---

【変換設定推奨値】
• サンプルレート: 16000Hz または 44100Hz
• ビット深度: 16bit
• チャンネル: モノラル（1チャンネル）推奨
• ファイルサイズ: 25MB以下

【YouTubeから音声抽出】
• yt-dlp --extract-audio --audio-format wav [URL]
"""
        
        text_widget = scrolledtext.ScrolledText(help_window, font=("", 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(1.0, help_text)
        text_widget.config(state=tk.DISABLED)
        
        close_button = tk.Button(help_window, text="閉じる", command=help_window.destroy)
        close_button.pack(pady=10)
    
    def load_saved_settings(self):
        """保存された設定を読み込み"""
        api_key = self.config_manager.get_api_key()
        if api_key:
            self.api_key_var.set(api_key)
            self.set_api_key(show_message=False)
    
    def set_api_key(self, show_message=True):
        """APIキーを設定"""
        api_key = self.api_key_var.get().strip()
        if not api_key:
            if show_message:
                messagebox.showwarning("警告", "APIキーを入力してください")
            return
        
        success = self.subtitle_gen.set_api_key(api_key)
        if success:
            self.config_manager.set_api_key(api_key)
            self.api_status_label.config(text="✓ 設定済み", fg="green")
            self.status_var.set("準備完了")
            if show_message:
                messagebox.showinfo("成功", "APIキーが正常に設定されました")
        else:
            self.api_status_label.config(text="✗ エラー", fg="red")
            self.status_var.set("APIキーエラー")
            if show_message:
                messagebox.showerror("エラー", "APIキーが無効です")
    
    def show_api_settings(self):
        """API設定ダイアログを表示"""
        dialog = tk.Toplevel(self.root)
        dialog.title("OpenAI API設定")
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        info_text = """OpenAI APIキーの取得方法：

1. https://platform.openai.com/ にアクセス
2. アカウントを作成またはログイン
3. API Keys ページに移動
4. "Create new secret key" をクリック
5. 生成されたキーをコピーして下記に入力

料金（目安）：
- Whisper API: $0.006/分（約0.9円/分）
- GPT-4翻訳: $0.03/1000トークン（約4.5円/1000文字）
"""
        
        tk.Label(dialog, text=info_text, justify=tk.LEFT, font=("", 10)).pack(padx=20, pady=10)
        
        key_frame = tk.Frame(dialog)
        key_frame.pack(padx=20, pady=10, fill=tk.X)
        
        tk.Label(key_frame, text="APIキー:").pack(side=tk.LEFT)
        key_entry = tk.Entry(key_frame, textvariable=self.api_key_var, width=50)
        key_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="設定", 
                 command=lambda: [self.set_api_key(), dialog.destroy()]).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="キャンセル", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def update_progress(self, message):
        """プログレス表示を更新"""
        self.progress_var.set(message)
        self.root.update()
    
    def open_file(self):
        """WAVファイルを開いて処理"""
        if self.subtitle_gen.client is None:
            messagebox.showerror("エラー", "OpenAI APIキーを設定してください")
            return
        
        file_path = filedialog.askopenfilename(
            title="英語WAVファイルを選択",
            filetypes=[
                ("WAVファイル", "*.wav"),
                ("すべてのファイル", "*.*")
            ]
        )
        
        if file_path:
            self.status_var.set("処理中...")
            
            def process_thread():
                try:
                    result = self.subtitle_gen.process_wav_file(file_path, self.update_progress)
                    
                    if isinstance(result, str):
                        # エラーの場合
                        messagebox.showerror("エラー", result)
                        self.status_var.set("エラー")
                        return
                    
                    # 成功の場合
                    self.current_segments = result['segments']
                    self.display_results(result, os.path.basename(file_path))
                    self.status_var.set("処理完了")
                    self.progress_var.set("")
                    
                except Exception as e:
                    messagebox.showerror("エラー", f"処理中にエラーが発生しました: {e}")
                    self.status_var.set("エラー")
                    self.progress_var.set("")
            
            threading.Thread(target=process_thread, daemon=True).start()
    
    def display_results(self, result, filename):
        """結果を各タブに表示"""
        segments = result['segments']
        
        # 対訳テキスト表示
        bilingual_content = self.subtitle_gen.generate_bilingual_text(segments)
        bilingual_content = f"ファイル: {filename}\n\n" + bilingual_content
        self.bilingual_text.delete(1.0, tk.END)
        self.bilingual_text.insert(1.0, bilingual_content)
        
        # SRT字幕表示
        srt_content = self.subtitle_gen.generate_srt_content(segments)
        self.srt_text.delete(1.0, tk.END)
        self.srt_text.insert(1.0, srt_content)
        
        # 日本語のみ表示
        japanese_content = f"ファイル: {filename}\n"
        japanese_content += "=" * 50 + "\n\n"
        for i, segment in enumerate(segments, 1):
            japanese_content += f"{i:02d}. {segment['japanese']}\n\n"
        
        self.japanese_text.delete(1.0, tk.END)
        self.japanese_text.insert(1.0, japanese_content)
    
    def save_srt(self):
        """SRT字幕ファイルを保存"""
        if not self.current_segments:
            messagebox.showwarning("警告", "保存する字幕データがありません")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="SRT字幕ファイルを保存",
            defaultextension=".srt",
            filetypes=[("SRT字幕ファイル", "*.srt"), ("すべてのファイル", "*.*")]
        )
        
        if file_path:
            try:
                srt_content = self.subtitle_gen.generate_srt_content(self.current_segments)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                messagebox.showinfo("成功", f"SRT字幕ファイルを保存しました:\n{os.path.basename(file_path)}")
                self.status_var.set(f"SRT保存完了: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("エラー", f"保存中にエラーが発生しました: {e}")
    
    def save_bilingual_text(self):
        """対訳テキストファイルを保存"""
        if not self.current_segments:
            messagebox.showwarning("警告", "保存するテキストデータがありません")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="対訳テキストファイルを保存",
            defaultextension=".txt",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")]
        )
        
        if file_path:
            try:
                text_content = self.subtitle_gen.generate_bilingual_text(self.current_segments)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                messagebox.showinfo("成功", f"対訳テキストファイルを保存しました:\n{os.path.basename(file_path)}")
                self.status_var.set(f"テキスト保存完了: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("エラー", f"保存中にエラーが発生しました: {e}")
    
    def clear_result(self):
        """結果をクリア"""
        self.bilingual_text.delete(1.0, tk.END)
        self.srt_text.delete(1.0, tk.END)
        self.japanese_text.delete(1.0, tk.END)
        self.current_segments = None
        self.progress_var.set("")
        self.status_var.set("クリア完了")
    
    def run(self):
        """GUIを開始"""
        self.root.mainloop()

class ConfigManager:
    def __init__(self):
        if not IMPORTS_OK:
            return
        self.config_file = "subtitle_config.ini"
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """設定を読み込み"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
    
    def save_config(self):
        """設定を保存"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def get_api_key(self):
        """APIキーを取得"""
        return self.config.get('openai', 'api_key', fallback='')
    
    def set_api_key(self, api_key):
        """APIキーを設定"""
        if 'openai' not in self.config:
            self.config.add_section('openai')
        self.config.set('openai', 'api_key', api_key)
        self.save_config()

def install_requirements():
    """必要なライブラリをインストール"""
    import subprocess
    import sys
    
    required_packages = [
        'openai>=1.0.0'
    ]
    
    print("必要なライブラリをインストール中...")
    print("=" * 40)
    
    for package in required_packages:
        try:
            print(f"📦 {package} をインストール中...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ {package} インストール完了")
        except subprocess.CalledProcessError:
            print(f"❌ {package} インストール失敗")
    
    print("\n🎉 インストール完了！")
    print("📌 このバージョンはWAVファイル専用（超軽量版）")
    print("次のコマンドでツールを起動してください:")
    print("py wav_subtitle.py")
    input("\nEnterキーを押して終了...")

def main():
    """メイン関数"""
    print("英語音声→日本語字幕生成ツール（WAV専用・FFmpeg不要版）")
    print("=" * 70)
    
    # インポートエラーのチェック
    if not IMPORTS_OK:
        print("❌ 必要なライブラリがインストールされていません")
        print(f"エラー: {MISSING_MODULE}")
        print("\n📦 以下の方法でライブラリをインストールしてください:")
        print("\n方法1: 自動インストール")
        print("  py wav_subtitle.py --install")
        print("\n方法2: 手動インストール")
        print("  pip install openai>=1.0.0")
        print("\n💡 このバージョンは最軽量（OpenAI APIのみ必要）")
        input("\nEnterキーを押して終了...")
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == "--install":
        install_requirements()
        return
    
    try:
        app = SubtitleGeneratorGUI()
        app.run()
    except Exception as e:
        print(f"アプリケーションの起動に失敗しました: {e}")
        input("Enterキーを押して終了...")

if __name__ == "__main__":
    if not IMPORTS_OK and len(sys.argv) > 1 and sys.argv[1] == "--install":
        # インポートエラーがある場合でも--installは実行可能
        install_requirements()
    else:
        main()
