
import os
import sys

# 将项目根目录添加到路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models.models import Audio
from backend.models.database import db

app = create_app()

def cleanup_corrupted_audios():
    with app.app_context():
        # 查找时长为0或不可识别的音频
        corrupted_audios = Audio.query.filter((Audio.duration <= 0) | (Audio.deleted == False)).all()
        
        count = 0
        for audio in corrupted_audios:
            # 再次验证文件头是否为 RIFF (WAV)
            if os.path.exists(audio.file_path):
                try:
                    with open(audio.file_path, 'rb') as f:
                        header = f.read(4)
                        if header != b'RIFF':
                            print(f"标记损坏的音频为已删除: {audio.name} ({audio.file_path})")
                            audio.deleted = True
                            count += 1
                except Exception as e:
                    print(f"检查文件 {audio.file_path} 时出错: {e}")
            else:
                # 文件不存在，也标记为已删除
                print(f"文件不存在，标记为已删除: {audio.name} ({audio.file_path})")
                audio.deleted = True
                count += 1
        
        if count > 0:
            db.session.commit()
            print(f"共清理了 {count} 条损坏的音频记录。")
        else:
            print("没有发现损坏的音频记录。")

if __name__ == "__main__":
    cleanup_corrupted_audios()
