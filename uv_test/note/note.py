import webview
import os

class Api:
    def get_note(self):
        file_path = './note/note.txt'
        
        if not os.path.exists(file_path):
            return "note.txt 파일이 존재하지 않습니다."
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return content

if __name__ == '__main__':
    api = Api()
    
    webview.create_window(
        title='Note Viewer (pywebview)', 
        url='front/text.html', 
        js_api=api,
        width=650,
        height=500
    )
    
    # [수정] gui='gtk' 옵션을 명시하여 GTK 백엔드로 강제 가동합니다.
    webview.start(gui='gtk')