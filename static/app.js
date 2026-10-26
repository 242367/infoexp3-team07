async function loadMessages() {
    const r = await fetch('/api/messages');
    const xs = await r.json();

    document.querySelector('#messages').innerHTML = xs.map(x => `
        <article class="message">
            <b>${escapeHtml(x.name)}</b>
            <p>${escapeHtml(x.message)}</p>
            <div class="meta">#${x.id}</div>

            <button type="button" class="reply-button"
                data-id="${x.id}">返信する</button>

            <form class="reply-form" data-id="${x.id}" hidden>
                <input class="reply-name" maxlength="30"
                    placeholder="Nickname" required>
                <textarea class="reply-message" maxlength="300"
                    placeholder="返信内容" required></textarea>
                <button type="submit">返信を投稿</button>
                <button type="button" class="cancel-reply">キャンセル</button>
            </form>

            <div class="replies">
                ${(x.replies || []).map(reply => `
                    <div class="reply">
                        <b>${escapeHtml(reply.name)}</b>
                        <p>${escapeHtml(reply.message)}</p>
                        <div class="meta">↳ #${reply.id}</div>
                    </div>
                `).join('')}
            </div>
        </article>
    `).join('');
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

document.querySelector('#message').addEventListener('input', () => {
    const inputLength = document.querySelector('#inputlength');
    if (inputLength) {
        inputLength.textContent =
            document.querySelector('#message').value.length + '文字';
    }
});


document.querySelector('#form').addEventListener('submit', async e => {
    e.preventDefault();

    const name = document.querySelector('#name').value.trim();
    const message = document.querySelector('#message').value.trim();

    const r = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, message })
    });

    document.querySelector('#status').textContent =
        r.ok ? '投稿しました' : '投稿に失敗しました';

    if (r.ok) {
        document.querySelector('#message').value = '';
        const inputLength = document.querySelector('#inputlength');
        if (inputLength) inputLength.textContent = '0文字';
        await loadMessages();
    }
});

document.querySelector('#messages').addEventListener('click', async e => {
    const button = e.target.closest('button');
    if (!button) return;

    if (button.classList.contains('reply-button')) {
        const form = button.nextElementSibling;
        form.hidden = !form.hidden;
    }

    if (button.classList.contains('cancel-reply')) {
        button.closest('.reply-form').hidden = true;
    }
});

document.querySelector('#messages').addEventListener('submit', async e => {
    if (!e.target.matches('.reply-form')) return;
    e.preventDefault();

    const form = e.target;
    const id = form.dataset.id;
    const name = form.querySelector('.reply-name').value.trim();
    const message = form.querySelector('.reply-message').value.trim();

    const r = await fetch(`/api/messages/${id}/replies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, message })
    });

    if (r.ok) {
        await loadMessages();
    } else {
        alert('返信の投稿に失敗しました。');
    }
});

loadMessages();

