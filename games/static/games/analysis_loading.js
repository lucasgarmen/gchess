(function () {
    let activeRequest = null;
    let pendingNavigationTimer = null;

    function overlayElements() {
        return {
            overlay: document.getElementById('analysis-loading-overlay'),
            cancelButton: document.getElementById('cancel-analysis-loading'),
        };
    }

    function showLoading() {
        const elements = overlayElements();

        if (!elements.overlay) {
            return;
        }

        elements.overlay.hidden = false;
        document.body.classList.add('analysis-loading-active');
    }

    function hideLoading() {
        const elements = overlayElements();

        if (elements.overlay) {
            elements.overlay.hidden = true;
        }

        document.body.classList.remove('analysis-loading-active');
    }

    function bindCancelButton() {
        const elements = overlayElements();

        if (!elements.cancelButton || elements.cancelButton.dataset.analysisCancelBound === 'true') {
            return;
        }

        elements.cancelButton.dataset.analysisCancelBound = 'true';
        elements.cancelButton.addEventListener('click', function () {
            if (activeRequest) {
                activeRequest.abort();
                activeRequest = null;
            }

            if (pendingNavigationTimer) {
                window.clearTimeout(pendingNavigationTimer);
                pendingNavigationTimer = null;
            }

            window.stop();
            hideLoading();
        });
    }

    function copyScriptAttributes(source, target) {
        Array.from(source.attributes).forEach(function (attribute) {
            target.setAttribute(attribute.name, attribute.value);
        });
    }

    function runScript(script) {
        return new Promise(function (resolve, reject) {
            if (script.type && script.type !== 'text/javascript' && script.type !== 'module') {
                resolve();
                return;
            }

            const executable = document.createElement('script');
            copyScriptAttributes(script, executable);

            if (script.src) {
                executable.addEventListener('load', resolve, { once: true });
                executable.addEventListener('error', reject, { once: true });
            } else {
                executable.text = script.textContent;
            }

            script.replaceWith(executable);

            if (!script.src) {
                resolve();
            }
        });
    }

    async function replaceDocumentWithHtml(html, url) {
        const nextDocument = new DOMParser().parseFromString(html, 'text/html');

        document.documentElement.replaceWith(nextDocument.documentElement);
        window.history.pushState({}, '', url);

        const scripts = Array.from(document.scripts);

        for (const script of scripts) {
            await runScript(script);
        }
    }

    async function fetchAnalysis(url, options) {
        if (!window.fetch || !window.AbortController || !window.DOMParser) {
            window.location.href = url;
            return;
        }

        activeRequest = new AbortController();
        showLoading();

        try {
            const response = await fetch(url, {
                cache: 'no-store',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'text/html',
                    ...(options && options.headers ? options.headers : {}),
                },
                method: options && options.method ? options.method : 'GET',
                body: options ? options.body : null,
                signal: activeRequest.signal,
            });

            if (!response.ok) {
                throw new Error(`Analysis request failed with ${response.status}`);
            }

            const html = await response.text();
            await replaceDocumentWithHtml(html, response.url || url);
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }

            window.location.href = url;
        } finally {
            activeRequest = null;
        }
    }

    function submitWithLoading(action) {
        showLoading();

        pendingNavigationTimer = window.setTimeout(function () {
            pendingNavigationTimer = null;
            action();
        }, 50);
    }

    function bindLink(linkId, options) {
        const link = document.getElementById(linkId);

        bindCancelButton();

        if (!link) {
            return;
        }

        link.addEventListener('click', function (event) {
            event.preventDefault();

            if (options && options.navigate) {
                submitWithLoading(function () {
                    window.location.href = link.href;
                });
                return;
            }

            fetchAnalysis(link.href);
        });
    }

    function bindForm(formId, options) {
        const form = document.getElementById(formId);

        bindCancelButton();

        if (!form) {
            return;
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();

            if (options && options.navigate) {
                submitWithLoading(function () {
                    form.submit();
                });
                return;
            }

            fetchAnalysis(form.action || window.location.href, {
                method: form.method || 'POST',
                body: new FormData(form),
            });
        });
    }

    window.GChessAnalysisLoading = {
        bindForm: bindForm,
        bindLink: bindLink,
    };
}());
