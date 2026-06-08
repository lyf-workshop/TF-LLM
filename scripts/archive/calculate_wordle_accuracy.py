import json
import sys
import io
from pathlib import Path

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load JSON file
file_path = Path(__file__).parent.parent / 'KORGym' / 'results' / '33-wordle' / 'Qwen3-32B_33-wordle_level4.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'File: Qwen3-32B_33-wordle_level4.json')
print(f'Total games: {len(data)}')
print()

# Count success (score == 1)
success_count = sum(1 for item in data if item.get('score', 0) == 1)
print(f'Success: {success_count}')
print(f'Failed: {len(data) - success_count}')
print(f'Accuracy: {success_count/len(data)*100:.2f}%')
print()

# Analyze by word length
from collections import defaultdict
by_length = defaultdict(lambda: {'total': 0, 'success': 0})

for item in data:
    # Try to get word length from response
    response_text = ' '.join(item.get('response', []))
    
    # Extract answer word
    import re
    answer_match = re.search(r'Answer:\s*(\w+)', response_text, re.IGNORECASE)
    if answer_match:
        answer_word = answer_match.group(1).lower()
        word_len = len(answer_word)
        
        by_length[word_len]['total'] += 1
        if item.get('score', 0) == 1:
            by_length[word_len]['success'] += 1

print('=' * 60)
print('Accuracy by Word Length')
print('=' * 60)
for length in sorted(by_length.keys()):
    stats = by_length[length]
    total = stats['total']
    success = stats['success']
    acc = success / total * 100 if total > 0 else 0
    print(f'{length:2d} letters: {success:3d}/{total:3d} ({acc:5.1f}%)')

print('=' * 60)
