"""Cache the selected reader's weights. No timecard images are uploaded."""
from backend.recognizer import create_recognizer
if __name__=='__main__':
    reader=create_recognizer(local_only=False)
    if hasattr(reader,'warm_up'):
        reader.warm_up()
    print(f'{type(reader).__name__} cached. MODEL_LOCAL_ONLY=1 can now run without network access.')
