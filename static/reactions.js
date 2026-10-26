
(() => {
    'use strict';

    const messages = document.querySelector('#messages');
    if (!messages) return;

    const STORAGE_KEY = 'miniboard-reaction-client-id';
    const idPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

    function makeUuid() {
        if (typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }

        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;

        const h = Array.from(
            bytes,
            n => n.toString(16).padStart(2, '0')
        ).join('');

        return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
    }

    function getClientId() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved && idPattern.test(saved)) return saved;
        } catch (_) {
            // Storage may be blocked.
        }

        const newId = makeUuid();

        try {
            localStorage.setItem(STORAGE_KEY, newId);
        } catch (_) {
            // Continue with a temporary ID.
        }

        return newId;
    }

    const clientId = getClientId();

    const state = {
        types: [],
        byMessage: {}
    };

    const pending = new Set();
    let lastRequestId = 0;

    function getPostId(article) {
        const meta = article.querySelector(':scope > .meta');
        const match = meta?.textContent?.trim().match(/^#([0-9]+)/);

        return match ? Number(match[1]) : null;
    }

    function paintArticle(article, messageId) {
        let bar = article.querySelector(':scope > .reactions-bar');

        if (!bar) {
            bar = document.createElement('div');
            bar.className = 'reactions-bar';
            bar.setAttribute('aria-label', 'リアクション');
            article.append(bar);
        }

        const item = state.byMessage[String(messageId)] || {
            counts: {},
            mine: []
        };

        const mine = new Set(item.mine || []);
        const elements = [];

        for (const reaction of state.types) {
            const button = document.createElement('button');

            button.type = 'button';
            button.className = 'reaction-button';

            const active = mine.has(reaction.id);

            if (active) {
                button.classList.add('is-active');
            }

            button.setAttribute('aria-pressed', String(active));
            button.disabled = pending.has(messageId);

            button.textContent =
                `${reaction.emoji} ${reaction.label} ${item.counts?.[reaction.id] || 0}`;

            button.addEventListener(
                'click',
                () => toggle(messageId, reaction.id)
            );

            elements.push(button);
        }

        const error = document.createElement('span');
        error.className = 'reaction-error';
        error.setAttribute('role', 'alert');
        elements.push(error);

        bar.replaceChildren(...elements);
    }

    function paint() {
        for (const article of messages.querySelectorAll(
            ':scope > article.message'
        )) {
            const messageId = getPostId(article);

            if (messageId !== null) {
                paintArticle(article, messageId);
            }
        }
    }

    async function refresh() {
        const thisRequest = ++lastRequestId;

        try {
            const response = await fetch(
                `/api/reactions?client_id=${encodeURIComponent(clientId)}`
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (thisRequest !== lastRequestId) return;

            state.types = data.types;
            state.byMessage = data.by_message;

            paint();

        } catch (error) {
            console.error('Failed to get reactions:', error);
        }
    }

    async function toggle(messageId, reactionTypeId) {
        if (pending.has(messageId)) return;

        pending.add(messageId);
        paint();

        let errorText = '';

        try {
            const response = await fetch('/api/reactions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message_id: messageId,
                    reaction_type_id: reactionTypeId,
                    client_id: clientId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            // Ignore older in-flight GET responses.
            ++lastRequestId;

            state.byMessage[String(messageId)] = {
                counts: data.counts,
                mine: data.mine
            };

        } catch (error) {
            console.error('Failed to update reaction:', error);

            errorText = 'リアクションの更新に失敗しました';

        } finally {
            pending.delete(messageId);
            paint();

            if (errorText) {
                const article = Array.from(
                    messages.querySelectorAll(':scope > article.message')
                ).find(node => getPostId(node) === messageId);

                const errorLine = article?.querySelector(
                    ':scope > .reactions-bar > .reaction-error'
                );

                if (errorLine) {
                    errorLine.textContent = errorText;
                }
            }
        }
    }

    // Detect when the existing app.js redraws the message list.
    const observer = new MutationObserver(() => {
        paint();
        void refresh();
    });

    observer.observe(messages, {
        childList: true
    });

    window.miniBoardReactions = { refresh };

    void refresh();
})();
