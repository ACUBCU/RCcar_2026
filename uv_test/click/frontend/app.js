const countEl = document.getElementById('count');
const increaseButton = document.getElementById('increase');
const decreaseButton = document.getElementById('decrease');

function renderCount(count) {
    countEl.textContent = count;
}

async function requestCounter(path, options = {}) {
    const response = await fetch(path, {
        cache: 'no-store',
        ...options,
    });

    if (!response.ok) {
        throw new Error(`Counter request failed: ${response.status}`);
    }

    const payload = await response.json();
    renderCount(payload.count);
}

increaseButton.addEventListener('click', () => {
    requestCounter('/api/counter/increase', { method: 'POST' });
});

decreaseButton.addEventListener('click', () => {
    requestCounter('/api/counter/decrease', { method: 'POST' });
});

const counterEvents = new EventSource('/api/counter/events');

counterEvents.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data);
    renderCount(payload.count);
});

counterEvents.addEventListener('error', () => {
    requestCounter('/api/counter');
});