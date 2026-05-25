(function () {
    const form = document.getElementById('trainer-chat-form');

    if (!form || form.dataset.trainerChatBound === 'true') {
        return;
    }

    const input = document.getElementById('trainer-chat-input');
    const submitButton = document.getElementById('trainer-chat-submit');
    const log = document.getElementById('trainer-chat-log');
    let thinking = false;

    function uiText(key, fallback) {
        return typeof UI_TEXTS !== 'undefined' && UI_TEXTS[key] ? UI_TEXTS[key] : fallback;
    }

    function csrfToken() {
        const cookies = document.cookie.split(';');

        for (let cookie of cookies) {
            cookie = cookie.trim();

            if (cookie.startsWith('csrftoken=')) {
                return cookie.substring('csrftoken='.length);
            }
        }

        return '';
    }

    function currentMoves() {
        if (typeof SAVED_MOVES === 'undefined' || !Array.isArray(SAVED_MOVES)) {
            return [];
        }

        const index = typeof historyIndex === 'number' ? historyIndex : SAVED_MOVES.length;
        return SAVED_MOVES.slice(0, index);
    }

    function addMessage(message, type) {
        if (!log) {
            return;
        }

        const item = document.createElement('div');
        item.classList.add('trainer-chat-message', `trainer-chat-message-${type}`);
        item.dataset.messageType = type;
        item.innerText = message;
        log.appendChild(item);
        log.scrollTop = log.scrollHeight;
    }

    function updateControls() {
        if (submitButton) {
            submitButton.disabled = thinking;
            submitButton.innerText = thinking ? uiText('thinking', 'Pensando...') : uiText('ask', 'Perguntar');
        }

        if (input) {
            input.disabled = thinking;
        }
    }

    async function askCoach(question) {
        thinking = true;
        updateControls();
        addMessage(question, 'user');

        try {
            const response = await fetch('/trainer-chat/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({
                    question: question,
                    moves: currentMoves(),
                    player_color: 'white',
                    language: typeof UI_LANGUAGE !== 'undefined' ? UI_LANGUAGE : 'pt',
                }),
            });
            const data = await response.json();

            if (!response.ok || data.error) {
                addMessage(uiText('trainer_error', 'O treinador nao conseguiu responder agora.'), 'trainer');
                return;
            }

            addMessage(data.answer, 'trainer');
        } catch (error) {
            console.error('Erro ao perguntar ao treinador:', error);
            addMessage(uiText('trainer_error', 'O treinador nao conseguiu responder agora.'), 'trainer');
        } finally {
            thinking = false;
            updateControls();
        }
    }

    function submitQuestion() {
        const question = input ? input.value.trim() : '';

        if (!question || thinking) {
            return;
        }

        input.value = '';
        askCoach(question);
    }

    form.dataset.trainerChatBound = 'fallback';
    form.addEventListener('submit', function (event) {
        event.preventDefault();
        submitQuestion();
    });

    if (input) {
        input.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
                return;
            }

            event.preventDefault();
            submitQuestion();
        });
    }
}());
