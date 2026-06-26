// pywebview가 로드 완료될 때 발생하는 이벤트를 수신합니다.
window.addEventListener('pywebviewready', () => {
    const noteBox = document.getElementById('note-box');

    // note.py의 Api 클래스에 정의한 get_note() 함수를 직접 호출합니다. (비동기)
    pywebview.api.get_note()
        .then(content => {
            // 줄바꿈(\n)을 HTML 태그(<br>)로 변환하여 출력
            noteBox.innerHTML = content.replace(/\n/g, '<br>');
        })
        .catch(error => {
            console.error('Error:', error);
            noteBox.textContent = '노트 내용을 불러오는 데 실패했습니다.';
            noteBox.style.color = 'red';
        });
});