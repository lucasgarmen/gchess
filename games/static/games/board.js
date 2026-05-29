let historyIndex = SAVED_MOVES.length;
let lastMove = null;
let currentTurn = 'white';
let selectedSquare = null;
let moveNumber = 1;
let gameOver = false;
let promotionPending = false;
let dragState = null;
let suppressNextClick = false;
let finishedGameSynced = false;
let computerThinking = false;
let coachEnabled = false;
let trainerChatThinking = false;
let boardOrientation = playerColor();
let analysisMode = false;
let analysisBoardState = null;
let analysisGameState = null;
let analysisPositions = [];
let analysisPositionIndex = 0;
let queuedMove = null;
let multiplayerSyncFailures = 0;
let gameClock = typeof GAME_CLOCK !== 'undefined' ? GAME_CLOCK : null;
let drawOffer = typeof DRAW_OFFER !== 'undefined' ? DRAW_OFFER : null;
let timeoutSyncInProgress = false;
let moveSound = null;
let startSound = null;
const MOVE_SOUND_START_OFFSET = 0.45;
let gameAudioContext = null;
let moveSoundBuffer = null;
let startSoundBuffer = null;
let pendingStartSound = false;
let audioUnlockBound = false;
let gameStatePollingId = window.gchessGameStatePollingId || null;
let gameChatPollingId = window.gchessGameChatPollingId || null;
let gameStateLoading = false;
let pendingMoveSaveCount = 0;
let gameSocket = null;
let gameSocketConnected = false;
let gameSocketFallbackActive = false;
let gameSocketReconnectId = null;
let gameSocketReconnectAttempts = 0;
let gameSocketEverConnected = false;
let gameStateAuthWarningShown = false;
let gameChatAuthWarningShown = false;
let gameStateNetworkWarningShown = false;
let gameChatNetworkWarningShown = false;

const DRAG_PIECE_SCALE = 1.7;
const GAME_STATE_POLL_INTERVAL_MS = 1000;
const GAME_SOCKET_RECONNECT_BASE_MS = 1000;
const GAME_SOCKET_RECONNECT_MAX_MS = 30000;
const GAME_SOCKET_RECONNECT_JITTER_MS = 500;
const POLLING_LOG_PREFIX = '[gchess polling]';
const SOCKET_LOG_PREFIX = '[gchess ws]';
const COMPUTER_GAME_STATE_KEY = 'gchess-computer-game-state';

function pollingLog(message, details = {}) {
    console.log(POLLING_LOG_PREFIX, message, details);
}

function socketLog(message, details = {}) {
    console.log(SOCKET_LOG_PREFIX, message, details);
}

function socketWarn(message, details = {}) {
    console.warn(SOCKET_LOG_PREFIX, message, details);
}

function lastKnownMoveId() {
    const knownMove = SAVED_MOVES.length > 0 ? SAVED_MOVES[SAVED_MOVES.length - 1] : null;
    return knownMove && knownMove.id ? knownMove.id : null;
}

function currentUserId() {
    if (typeof CURRENT_USER_ID === 'undefined') {
        return null;
    }

    return Number(CURRENT_USER_ID) || null;
}

function isHomeComputerGame() {
    return isComputerMode() && typeof ANALYZER_MODE === 'undefined';
}

//Funcçao para redireccionar usuario que nao está logueado
function shouldStopPollingForAuth(response) {
    return response.redirected ||
        response.status === 401 ||
        response.status === 403 ||  //Caso nao esteja logueado ou receba erro, ele é redireccionado para /login
        response.url.includes('/accounts/login/');
}

//Funções para freiar auto polling
function stopGameStatePolling(reason) {
    if (gameStatePollingId) {
        clearInterval(gameStatePollingId);
        gameStatePollingId = null;
        window.gchessGameStatePollingId = null;
    }
    //Serve para mostrar o warning:
    if (!gameStateAuthWarningShown) {
        console.warn(reason);
        gameStateAuthWarningShown = true;
    }
}

function stopGameChatPolling(reason) {
    if (gameChatPollingId) {
        clearInterval(gameChatPollingId);
        gameChatPollingId = null;
        window.gchessGameChatPollingId = null;
    }
//freia autopolling do chats
    if (!gameChatAuthWarningShown) {
        console.warn(reason);
        gameChatAuthWarningShown = true;
    }
}

//Função para tradução de palavras individuais
function uiText(key, fallback) {
    if (typeof UI_TEXTS !== 'undefined' && UI_TEXTS[key]) {
        return UI_TEXTS[key];
    }

    return fallback;
}

//Variável usada para verificar se ainda o enroque é possivel
let castlingRights = {
    white: {
        kingMoved: false,
        leftRookMoved: false,
        rightRookMoved: false
    },
    black: {
        kingMoved: false,
        leftRookMoved: false,
        rightRookMoved: false
    }
};

const moveList = document.getElementById('move-list');
const board = document.getElementById('board');
const turnIndicator = document.getElementById('turn-indicator');
const gameStatus = document.getElementById('game-status');
const pgnPanel = document.querySelector('.pgn-panel');
const pgnBox = document.getElementById('pgn-box');
const whiteClock = document.getElementById('white-clock');
const blackClock = document.getElementById('black-clock');
const offerDrawButton = document.getElementById('offer-draw-button');
const resignButton = document.getElementById('resign-button');
const analyzeGameButton = document.getElementById('analyze-game-button');
const analyzeGameForm = document.getElementById('analyze-game-form');
const analyzeGamePgn = document.getElementById('analyze-game-pgn');
const resignConfirmPanel = document.getElementById('resign-confirm-panel');
const confirmResignButton = document.getElementById('confirm-resign-button');
const cancelResignButton = document.getElementById('cancel-resign-button');
const drawOfferPanel = document.getElementById('draw-offer-panel');
const drawOfferText = document.getElementById('draw-offer-text');
const drawOfferActions = document.getElementById('draw-offer-actions');
const acceptDrawButton = document.getElementById('accept-draw-button');
const rejectDrawButton = document.getElementById('reject-draw-button');
const gameChatToggle = document.getElementById('game-chat-toggle');
const gameChatCount = document.getElementById('game-chat-count');
const gameChatPanel = document.getElementById('game-chat-panel');
const gameChatMessages = document.getElementById('game-chat-messages');
const gameChatForm = document.getElementById('game-chat-form');
const gameChatInput = document.getElementById('game-chat-input');
const gameChatClose = document.getElementById('game-chat-close');
const gameChatEmojiToggle = document.getElementById('game-chat-emoji-toggle');
const gameChatEmojiPanel = document.getElementById('game-chat-emoji-panel');
let gameChatOpen = false;
let gameChatLoading = false;

const initialPosition = {
    a8: { type: 'rook', color: 'black' },
    b8: { type: 'horse', color: 'black' },
    c8: { type: 'bishop', color: 'black' },
    d8: { type: 'queen', color: 'black' },
    e8: { type: 'king', color: 'black' },
    f8: { type: 'bishop', color: 'black' },
    g8: { type: 'horse', color: 'black' },
    h8: { type: 'rook', color: 'black' },

    a7: { type: 'pawn', color: 'black' },
    b7: { type: 'pawn', color: 'black' },
    c7: { type: 'pawn', color: 'black' },
    d7: { type: 'pawn', color: 'black' },
    e7: { type: 'pawn', color: 'black' },
    f7: { type: 'pawn', color: 'black' },
    g7: { type: 'pawn', color: 'black' },
    h7: { type: 'pawn', color: 'black' },

    a2: { type: 'pawn', color: 'white' },
    b2: { type: 'pawn', color: 'white' },
    c2: { type: 'pawn', color: 'white' },
    d2: { type: 'pawn', color: 'white' },
    e2: { type: 'pawn', color: 'white' },
    f2: { type: 'pawn', color: 'white' },
    g2: { type: 'pawn', color: 'white' },
    h2: { type: 'pawn', color: 'white' },

    a1: { type: 'rook', color: 'white' },
    b1: { type: 'horse', color: 'white' },
    c1: { type: 'bishop', color: 'white' },
    d1: { type: 'queen', color: 'white' },
    e1: { type: 'king', color: 'white' },
    f1: { type: 'bishop', color: 'white' },
    g1: { type: 'horse', color: 'white' },
    h1: { type: 'rook', color: 'white' },
};

//função para implementar sonido nos movimentos
function buildSound(url, volume = 1) {
    if (!url || typeof Audio === 'undefined') {  //en caso de erro ou falta de som, nao retorna som
        return null;
    }

    const audio = new Audio(url);
    audio.preload = 'auto';
    audio.volume = volume;
    audio.load();
    return audio;
}
//função especifica de audio
function getGameAudioContext() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) {
        return null;
    }

    if (!gameAudioContext) {
        gameAudioContext = new AudioContextClass();
    }

    return gameAudioContext;
}

//função para ter o som preparado para uso (precarregado)
async function preloadSoundBuffer(url) {
    const audioContext = getGameAudioContext();

    if (!url || !audioContext || typeof fetch === 'undefined') {
        return null;
    }

    try {
        const response = await fetch(url, { cache: 'force-cache' });
        const arrayBuffer = await response.arrayBuffer();
        return await audioContext.decodeAudioData(arrayBuffer);
    } catch (error) {
        console.warn('No se pudo precargar el sonido:', error);
        return null;
    }
}

//Utiliza sonido precarregado
function playBuffer(buffer, startOffset = 0, volume = 1) {
    const audioContext = getGameAudioContext();

    if (!buffer || !audioContext) {
        return false;
    }

    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }

    const source = audioContext.createBufferSource();
    const gain = audioContext.createGain();
    source.buffer = buffer;
    gain.gain.value = volume;
    source.connect(gain);
    gain.connect(audioContext.destination);
    source.start(0, Math.min(startOffset, buffer.duration));
    return true;
}

//realiza som em caso de nao conseguir implementar o playBuffer
function playAudio(audio, startOffset = 0) {
    if (!audio) {
        return Promise.resolve(false);
    }

    audio.currentTime = startOffset;
    return audio.play()
        .then(() => true)
        .catch(() => false);
}

function unlockStartSoundOnFirstInteraction() {
    if (audioUnlockBound || !pendingStartSound) {
        return;
    }

    audioUnlockBound = true;

    const retryStartSound = () => {
        pendingStartSound = false;
        playAudio(startSound);
        window.removeEventListener('pointerdown', retryStartSound);
        window.removeEventListener('keydown', retryStartSound);
    };

    // em caso de bloqueio de audio em navegador, usa som de inicio
    window.addEventListener('pointerdown', retryStartSound, { once: true });
    window.addEventListener('keydown', retryStartSound, { once: true });
}

//som do começo de partida
function playStartSound() {
    const playedFromBuffer = playBuffer(startSoundBuffer);

    if (playedFromBuffer) {
        return;
    }

    playAudio(startSound).then((played) => {
        if (!played) {
            pendingStartSound = true;
            unlockStartSoundOnFirstInteraction();
        }
    });
}

//função de movimento de peças
function playMoveSound() {
    if (!playBuffer(moveSoundBuffer, MOVE_SOUND_START_OFFSET)) {
        playAudio(moveSound, MOVE_SOUND_START_OFFSET);
    }
}

const letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

//Peças faltantes
const pieceFallbacks = {
    queen_white: '♕',
    queen_black: '♛',
};

const pieceFileNames = {
    pawn_white: 'pawn_white.png',
};

const pieceValues = {
    queen: 9,
    rook: 5,
    bishop: 3,
    horse: 3,
    pawn: 1,
    king: 0,
};

const pieceOrder = ['queen', 'rook', 'bishop', 'horse', 'pawn'];

function squareColor(square) {
    return square.dataset.color || '';
}

function sameColor(square1, square2) {
    return squareColor(square1) !== '' && squareColor(square1) === squareColor(square2);
}

function isKingSquare(square) {
    return square && square.dataset.type === 'king';
}

function isComputerMode() {
    return typeof COMPUTER_MODE !== 'undefined' && COMPUTER_MODE;
}

function playerColor() {
    if (typeof GAME_PLAYER_COLOR !== 'undefined' && GAME_PLAYER_COLOR) {
        return GAME_PLAYER_COLOR;
    }

    return typeof PLAYER_COLOR !== 'undefined' ? PLAYER_COLOR : 'white';
}

function isMultiplayerMode() {
    return typeof MULTIPLAYER_MODE !== 'undefined' && MULTIPLAYER_MODE;
}

function computerColor() {
    return playerColor() === 'white' ? 'black' : 'white';
}

function canPlayerMoveFrom(square) {
    if (analysisMode) {
        return squareColor(square) !== '';
    }

    if (
        !isViewingLatestPosition() ||
        gameOver ||
        computerThinking ||
        squareColor(square) !== currentTurn
    ) {
        return false;
    }

    if (isMultiplayerMode()) {
        return currentTurn === playerColor();
    }

    return !isComputerMode() || currentTurn === playerColor();
}

//Deixa a jogada pronta, mas nao consegue mover caso nao seja sua hora.
function canQueueMoveFrom(square) {
    return isMultiplayerMode() &&
        !analysisMode &&
        isViewingLatestPosition() &&
        !gameOver &&
        !promotionPending &&
        currentTurn !== playerColor() &&
        squareColor(square) === playerColor();
}

//atualizador de estado do card
function updateTurnIndicator() {
    if (analysisMode) {
        turnIndicator.innerText = uiText('analysis_mode_testing', 'Modo análisis: pruebas temporarias');
        return;
    }

    if (gameOver && isViewingLatestPosition()) {
        turnIndicator.innerText = 'Partida finalizada';
        return;
    }

    if (computerThinking) {
        turnIndicator.innerText = 'Computador pensando...';
        return;
    }

    if (isViewingLatestPosition()) {
        turnIndicator.innerText = currentTurn === 'white'
            ? uiText('turn_white', 'Vez das brancas')
            : uiText('turn_black', 'Vez das pretas');
    } else {
        turnIndicator.innerText = `Vendo jogada ${historyIndex} de ${SAVED_MOVES.length}`;
    }
}

function isViewingLatestPosition() {
    return historyIndex === SAVED_MOVES.length;
}

function boardOrderFor(square) {
    const coord = square.dataset.coord;
    const fileIndex = letters.indexOf(coord[0]);
    const rank = parseInt(coord[1]);

    if (boardOrientation === 'black') {
        return (rank - 1) * 8 + (7 - fileIndex);
    }

    return (8 - rank) * 8 + fileIndex;
}

function updateBoardLabels() {
    const rankLabels = document.querySelectorAll('.rank-labels span');
    const fileLabels = document.querySelectorAll('.file-labels span');
    const ranks = boardOrientation === 'black'
        ? ['1', '2', '3', '4', '5', '6', '7', '8']
        : ['8', '7', '6', '5', '4', '3', '2', '1'];
    const files = boardOrientation === 'black'
        ? [...letters].reverse()
        : letters;

    rankLabels.forEach((label, index) => {
        label.innerText = ranks[index];
    });

    fileLabels.forEach((label, index) => {
        label.innerText = files[index];
    });
}

function updateBoardOrientation() {
    document.querySelectorAll('.square').forEach(square => {
        square.style.order = boardOrderFor(square);
    });
    updateBoardLabels();
}

function flipBoard() {
    boardOrientation = boardOrientation === 'white' ? 'black' : 'white';
    updateBoardOrientation();
}

function snapshotBoardData() {
    return Array.from(document.querySelectorAll('.square')).map(square => ({
        coord: square.dataset.coord,
        color: square.dataset.color,
        type: square.dataset.type,
    }));
}

function restoreBoardData(boardData) {
    boardData.forEach(state => {
        const square = getSquare(state.coord);

        square.replaceChildren();
        square.dataset.color = state.color;
        square.dataset.type = state.type;

        if (state.color && state.type) {
            square.appendChild(createPieceElement({
                color: state.color,
                type: state.type,
            }));
        }
    });
}

function recordAnalysisPosition() {
    analysisPositions = analysisPositions.slice(0, analysisPositionIndex + 1);
    analysisPositions.push(snapshotBoardData());
    analysisPositionIndex = analysisPositions.length - 1;
    updateHistoryControls();
}

function showAnalysisPosition(nextIndex) {
    if (!analysisMode || nextIndex < 0 || nextIndex >= analysisPositions.length) {
        return;
    }

    clearSelection();
    analysisPositionIndex = nextIndex;
    restoreBoardData(analysisPositions[analysisPositionIndex]);
    updateCapturedMaterial();
    updateHistoryControls();
}

function showPreviousAnalysisPosition() {
    showAnalysisPosition(analysisPositionIndex - 1);
}

function showNextAnalysisPosition() {
    showAnalysisPosition(analysisPositionIndex + 1);
}

function enterAnalysisMode() {
    if (computerThinking || promotionPending) {
        return;
    }

    clearQueuedMove();
    clearSelection();
    analysisBoardState = snapshotBoard();
    analysisGameState = {
        currentTurn: currentTurn,
        lastMove: lastMove,
        gameOver: gameOver,
        moveNumber: moveNumber,
        historyIndex: historyIndex,
        castlingRights: JSON.parse(JSON.stringify(castlingRights)),
    };
    analysisPositions = [snapshotBoardData()];
    analysisPositionIndex = 0;
    analysisMode = true;
    board.classList.add('analysis-board');
    hideGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function exitAnalysisMode() {
    if (!analysisMode) {
        return;
    }

    clearSelection();
    restoreBoard(analysisBoardState);
    currentTurn = analysisGameState.currentTurn;
    lastMove = analysisGameState.lastMove;
    gameOver = analysisGameState.gameOver;
    moveNumber = analysisGameState.moveNumber;
    historyIndex = analysisGameState.historyIndex;
    castlingRights = analysisGameState.castlingRights;
    analysisMode = false;
    analysisBoardState = null;
    analysisGameState = null;
    analysisPositions = [];
    analysisPositionIndex = 0;
    board.classList.remove('analysis-board');
    refreshGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function toggleAnalysisMode() {
    if (analysisMode) {
        exitAnalysisMode();
    } else {
        enterAnalysisMode();
    }
}

function resetCastlingRights() {
    castlingRights = {
        white: {
            kingMoved: false,
            leftRookMoved: false,
            rightRookMoved: false
        },
        black: {
            kingMoved: false,
            leftRookMoved: false,
            rightRookMoved: false
        }
    };
}

function updateCastlingRightsAfterMove(move) {
    const movingType = move.piece_type;
    const movingColor = move.piece_color;
    const from = move.from;

    if (movingType === 'king') {
        castlingRights[movingColor].kingMoved = true;
    }

    if (movingType === 'rook') {
        if (from === 'a1') castlingRights.white.leftRookMoved = true;
        if (from === 'h1') castlingRights.white.rightRookMoved = true;
        if (from === 'a8') castlingRights.black.leftRookMoved = true;
        if (from === 'h8') castlingRights.black.rightRookMoved = true;
    }
}

function updateHistoryControls() {
    const lastMoveButton = document.getElementById('last-move');

    document.getElementById('prev-move').disabled = analysisMode || historyIndex === 0;
    document.getElementById('next-move').disabled = analysisMode || historyIndex === SAVED_MOVES.length;

    if (lastMoveButton) {
        lastMoveButton.disabled = analysisMode || (
            typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE
                ? historyIndex === 0
                : isViewingLatestPosition()
        );
    }

    const undoComputerButton = document.getElementById('undo-computer-move');
    if (undoComputerButton) {
        undoComputerButton.disabled = analysisMode || computerThinking || SAVED_MOVES.length === 0;
    }

    const resetComputerButton = document.getElementById('reset-computer-game');
    if (resetComputerButton) {
        resetComputerButton.disabled = analysisMode || computerThinking || SAVED_MOVES.length === 0;
    }

    const toggleCoachButton = document.getElementById('toggle-coach');
    if (toggleCoachButton) {
        toggleCoachButton.innerText = coachEnabled
            ? uiText('disable_coach', 'Desabilitar treinador')
            : uiText('enable_coach', 'Habilitar treinador');
    }

    const playerColorSelect = document.getElementById('player-color');
    if (playerColorSelect) {
        playerColorSelect.disabled = analysisMode || computerThinking || SAVED_MOVES.length > 0;
    }

    const analysisModeButton = document.getElementById('toggle-analysis-mode');
    if (analysisModeButton) {
        analysisModeButton.innerText = analysisMode
            ? uiText('exit_analysis_mode', 'Salir análisis')
            : uiText('analysis_mode', 'Modo análisis');
        analysisModeButton.classList.toggle('active', analysisMode);
    }

    const analysisPrevButton = document.getElementById('analysis-prev');
    if (analysisPrevButton) {
        analysisPrevButton.hidden = !analysisMode;
        analysisPrevButton.disabled = analysisPositionIndex === 0;
    }

    const analysisNextButton = document.getElementById('analysis-next');
    if (analysisNextButton) {
        analysisNextButton.hidden = !analysisMode;
        analysisNextButton.disabled = analysisPositionIndex >= analysisPositions.length - 1;
    }
}

function showGameStatus(message) {
    gameStatus.innerText = message;
    gameStatus.hidden = false;
    updateFinishedPanelState();

    if (analyzeGameButton && gameOver) {
        analyzeGameButton.hidden = false;
    }
}

function hideGameStatus() {
    gameStatus.hidden = true;
    gameStatus.innerText = '';
    updateFinishedPanelState();

    if (analyzeGameButton && !gameOver) {
        analyzeGameButton.hidden = true;
    }
}

function updateFinishedPanelState() {
    if (!pgnPanel) {
        return;
    }

    pgnPanel.classList.toggle('game-finished-panel', gameOver);
}

function initialPieceCounts() {
    const counts = {
        white: {},
        black: {},
    };

    Object.values(initialPosition).forEach(piece => {
        counts[piece.color][piece.type] = (counts[piece.color][piece.type] || 0) + 1;
    });

    return counts;
}

function currentPieceCounts() {
    const counts = {
        white: {},
        black: {},
    };

    document.querySelectorAll('.square').forEach(square => {
        const color = square.dataset.color;
        const type = square.dataset.type;

        if (!color || !type || type === 'king') {
            return;
        }

        counts[color][type] = (counts[color][type] || 0) + 1;
    });

    return counts;
}

function capturedPiecesFor(color) {
    const initialCounts = initialPieceCounts();
    const currentCounts = currentPieceCounts();
    const captured = [];

    pieceOrder.forEach(type => {
        const missing = (initialCounts[color][type] || 0) - (currentCounts[color][type] || 0);

        for (let i = 0; i < missing; i++) {
            captured.push({ type: type, color: color });
        }
    });

    return captured;
}

function materialValue(pieces) {
    return pieces.reduce((total, piece) => total + (pieceValues[piece.type] || 0), 0);
}

function renderCapturedPieces(containerId, pieces) {
    const container = document.getElementById(containerId);

    if (!container) {
        return;
    }

    container.replaceChildren();

    pieces.forEach(piece => {
        const pieceElement = createPieceElement(piece);
        pieceElement.classList.add('captured-piece');
        container.appendChild(pieceElement);
    });
}

function updateCapturedMaterial() {
    const capturedBlack = capturedPiecesFor('black');
    const capturedWhite = capturedPiecesFor('white');
    const whiteCapturedValue = materialValue(capturedBlack);
    const blackCapturedValue = materialValue(capturedWhite);
    const advantage = whiteCapturedValue - blackCapturedValue;
    const whiteAdvantage = document.getElementById('white-material-advantage');
    const blackAdvantage = document.getElementById('black-material-advantage');

    renderCapturedPieces('captured-black', capturedBlack);
    renderCapturedPieces('captured-white', capturedWhite);

    if (whiteAdvantage) {
        whiteAdvantage.innerText = advantage > 0 ? `+${advantage}` : '';
    }

    if (blackAdvantage) {
        blackAdvantage.innerText = advantage < 0 ? `+${Math.abs(advantage)}` : '';
    }
}

function selectSquare(square) {
    selectedSquare = square;
    square.classList.add('selected');

    const moves = canQueueMoveFrom(square) ? getPremoveMoves(square) : getLegalMoves(square);
    highlightMoves(moves, { allowOwnPieces: canQueueMoveFrom(square) });
}

function clearQueuedMove() {
    if (queuedMove) {
        getSquare(queuedMove.from)?.classList.remove('queued-move-origin');
        getSquare(queuedMove.to)?.classList.remove('queued-move-target');
    }

    queuedMove = null;
}

function queueMove(fromSquare, toSquare) {
    clearQueuedMove();
    queuedMove = {
        from: fromSquare.dataset.coord,
        to: toSquare.dataset.coord,
    };
    fromSquare.classList.add('queued-move-origin');
    toSquare.classList.add('queued-move-target');
    clearSelection();
}

function clearSelection() {
    if (selectedSquare !== null) {
        selectedSquare.classList.remove('selected');
    }

    document.querySelectorAll('.possible-move').forEach(square => {
        square.classList.remove('possible-move');
    });

    selectedSquare = null;
}

function switchTurn() {
    currentTurn = currentTurn === 'white' ? 'black' : 'white';
    updateTurnIndicator();
}


function movePiece(fromSquare, toSquare) {
    toSquare.replaceChildren(...fromSquare.childNodes);
    toSquare.dataset.color = fromSquare.dataset.color;
    toSquare.dataset.type = fromSquare.dataset.type;

    fromSquare.replaceChildren();
    fromSquare.dataset.color = '';
    fromSquare.dataset.type = '';
}

async function playAnalysisMove(fromSquare, toSquare, shouldAnimate = true) {
    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;
    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;
    const isEnPassantCapture = movingType === 'pawn' && from[0] !== to[0] && toSquare.dataset.color === '';

    if (shouldAnimate) {
        await animateMove(fromSquare, toSquare);
    }

    if (
        isEnPassantCapture
    ) {
        const capturedPawnSquare = getSquare(to[0] + from[1]);

        if (capturedPawnSquare) {
            capturedPawnSquare.replaceChildren();
            capturedPawnSquare.dataset.color = '';
            capturedPawnSquare.dataset.type = '';
        }
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
    playMoveSound();

    if (isPromotionMove(movingType, movingColor, to)) {
        const promotedType = await choosePromotionPiece(toSquare, movingColor);
        promotePawn(toSquare, movingColor, promotedType);
    }

    clearSelection();
    recordAnalysisPosition();
    updateCapturedMaterial();
}

function isPromotionMove(pieceType, pieceColor, toCoord) {
    if (pieceType !== 'pawn') {
        return false;
    }

    const promotionRow = pieceColor === 'white' ? 8 : 1;

    return getRow(toCoord) === promotionRow;
}

function promotePawn(square, color, promotedType) {
    square.dataset.type = promotedType;
    square.replaceChildren(
        createPieceElement({
            type: promotedType,
            color: color
        })
    );
}

function getSquareFromPoint(x, y) {
    const element = document.elementFromPoint(x, y);

    return element ? element.closest('.square') : null;
}

function createDragPiece(square, event) {
    const piece = square.firstElementChild;

    if (!piece) {
        return null;
    }

    const squareRect = square.getBoundingClientRect();
    const dragPiece = piece.cloneNode(true);

    dragPiece.classList.add('drag-piece');
    dragPiece.style.left = '0';
    dragPiece.style.top = '0';
    dragPiece.style.width = `${squareRect.width * DRAG_PIECE_SCALE}px`;
    dragPiece.style.height = `${squareRect.height * DRAG_PIECE_SCALE}px`;
    dragPiece.draggable = false;

    document.body.appendChild(dragPiece);
    square.classList.add('drag-origin');

    moveDragPiece(dragPiece, event);

    return dragPiece;
}

function moveDragPiece(dragPiece, event) {
    dragPiece.style.transform = `translate(${event.clientX - dragPiece.offsetWidth / 2}px, ${event.clientY - dragPiece.offsetHeight / 2}px)`;
}

function cleanupDragState() {
    if (!dragState) {
        return;
    }

    document.removeEventListener('pointermove', handlePieceDrag);
    document.removeEventListener('pointerup', finishPieceDrag);
    document.removeEventListener('pointercancel', cancelPieceDrag);
    window.removeEventListener('blur', cancelPieceDrag);

    if (dragState.pointerId !== null && dragState.originSquare.hasPointerCapture?.(dragState.pointerId)) {
        dragState.originSquare.releasePointerCapture(dragState.pointerId);
    }

    dragState.originSquare.classList.remove('drag-origin');
    dragState.dragPiece.remove();
    dragState = null;
}

function animateMove(fromSquare, toSquare) {
    const piece = fromSquare.firstElementChild;

    if (!piece || !piece.animate) {
        return Promise.resolve();
    }

    const fromRect = fromSquare.getBoundingClientRect();
    const toRect = toSquare.getBoundingClientRect();
    const pieceRect = piece.getBoundingClientRect();
    const movingPiece = piece.cloneNode(true);

    movingPiece.classList.add('move-animation-piece');
    movingPiece.style.left = `${pieceRect.left}px`;
    movingPiece.style.top = `${pieceRect.top}px`;
    movingPiece.style.width = `${pieceRect.width}px`;
    movingPiece.style.height = `${pieceRect.height}px`;

    document.body.appendChild(movingPiece);
    fromSquare.classList.add('drag-origin');

    return movingPiece.animate(
        [
            { transform: 'translate(0, 0)' },
            { transform: `translate(${toRect.left - fromRect.left}px, ${toRect.top - fromRect.top}px)` }
        ],
        {
            duration: 180,
            easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)'
        }
    ).finished.finally(() => {
        fromSquare.classList.remove('drag-origin');
        movingPiece.remove();
    });
}

async function playMove(fromSquare, toSquare, shouldAnimate = true, forcedPromotion = null) {
    clearQueuedMove();

    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;

    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;
    const isEnPassantCapture = movingType === 'pawn' && from[0] !== to[0] && toSquare.dataset.color === '';

    if (shouldAnimate) {
        await animateMove(fromSquare, toSquare);
    }

    // comer al paso
    if (
        isEnPassantCapture
    ) {
        const capturedPawnCoord = to[0] + from[1];
        const capturedPawnSquare = document.querySelector(`[data-coord="${capturedPawnCoord}"]`);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    // enroque
    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
    playMoveSound();

    let promotedType = null;

    // promoção de peão
    if (isPromotionMove(movingType, movingColor, to)) {
        promotedType = forcedPromotion || await choosePromotionPiece(toSquare, movingColor);
        promotePawn(toSquare, movingColor, promotedType);
    }

    const playedMove = {
        move_number: moveNumber,
        from: from,
        to: to,
        piece_type: movingType,
        piece_color: movingColor,
        promotion: promotedType || null
    };

    if (isComputerMode()) {
        const eloSelect = document.getElementById('computer-elo');
        if (eloSelect) {
            eloSelect.disabled = true;
        }
    }

    updateCastlingRightsAfterMove(playedMove);
    lastMove = playedMove;

    SAVED_MOVES.push(playedMove);
    historyIndex = SAVED_MOVES.length;
    moveNumber = SAVED_MOVES.length + 1;

    clearSelection();
    switchTurn();

    const gameOutcome = checkGameEnd();
    const gameEnded = Boolean(gameOutcome);

    renderSavedMoveList();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();

    saveMoveToDatabase(playedMove, {
        finished: gameEnded,
        winner: gameOutcome?.winner || null,
        result: gameOutcome?.result || null,
    });

    if (isComputerMode() && coachEnabled && movingColor === playerColor()) {
        requestCoachAnalysis();
    }

    if (
        isComputerMode() &&
        !gameEnded &&
        currentTurn === computerColor()
    ) {
        await askComputerMove();
    }
}

async function playQueuedMoveIfReady() {
    if (
        !queuedMove ||
        !isMultiplayerMode() ||
        analysisMode ||
        gameOver ||
        promotionPending ||
        currentTurn !== playerColor() ||
        !isViewingLatestPosition()
    ) {
        return;
    }

    const fromSquare = getSquare(queuedMove.from);
    const toSquare = getSquare(queuedMove.to);

    if (
        !fromSquare ||
        !toSquare ||
        squareColor(fromSquare) !== playerColor() ||
        !getLegalMoves(fromSquare).includes(queuedMove.to)
    ) {
        clearQueuedMove();
        clearSelection();
        return;
    }

    await playMove(fromSquare, toSquare);
}

function startPieceDrag(square, event) {
    if (promotionPending) {
        return;
    }

    if (
        selectedSquare !== null &&
        selectedSquare !== square &&
        isPossibleMove(square)
    ) {
        return;
    }

    event.preventDefault();

    cleanupDragState();

    const dragPiece = createDragPiece(square, event);

    if (!dragPiece) {
        return;
    }

    clearSelection();
    suppressNextClick = true;

    const canPlayFromSquare = canPlayerMoveFrom(square);
    const canQueueFromSquare = canQueueMoveFrom(square);

    if (canPlayFromSquare || canQueueFromSquare) {
        selectSquare(square);
    }

    dragState = {
        originSquare: square,
        dragPiece: dragPiece,
        pointerId: event.pointerId ?? null,
        canPlayFromSquare: canPlayFromSquare,
        canQueueFromSquare: canQueueFromSquare,
        startX: event.clientX,
        startY: event.clientY
    };

    if (event.pointerId !== undefined && square.setPointerCapture) {
        square.setPointerCapture(event.pointerId);
    }

    document.addEventListener('pointermove', handlePieceDrag);
    document.addEventListener('pointerup', finishPieceDrag);
    document.addEventListener('pointercancel', cancelPieceDrag);
    window.addEventListener('blur', cancelPieceDrag);
}

function handlePieceDrag(event) {
    if (!dragState) {
        return;
    }

    if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) {
        return;
    }

    event.preventDefault();
    moveDragPiece(dragState.dragPiece, event);
}

async function finishPieceDrag(event) {
    if (!dragState) {
        return;
    }

    if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) {
        return;
    }

    event.preventDefault();

    const originSquare = dragState.originSquare;
    const targetSquare = getSquareFromPoint(event.clientX, event.clientY);
    const canPlayFromSquare = dragState.canPlayFromSquare;
    const canQueueFromSquare = dragState.canQueueFromSquare;
    const dragDistance = Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY);
    const isTap = dragDistance < 8;

    cleanupDragState();

    if (isTap) {
        clearSelection();
        if (canPlayFromSquare || canQueueFromSquare) {
            selectSquare(originSquare);
        }
        return;
    }

    if (!canPlayFromSquare) {
        if (canQueueFromSquare && targetSquare && targetSquare !== originSquare && isPossibleMove(targetSquare)) {
            queueMove(originSquare, targetSquare);
            return;
        }

        clearSelection();
        return;
    }

    if (targetSquare === originSquare) {
        clearSelection();
        if (canPlayFromSquare || canQueueFromSquare) {
            selectSquare(originSquare);
        }
        return;
    }

    if (!targetSquare || !isPossibleMove(targetSquare)) {
        clearSelection();
        return;
    }

    if (analysisMode) {
        await playAnalysisMove(originSquare, targetSquare, false);
    } else {
        await playMove(originSquare, targetSquare, false);
    }
}

function cancelPieceDrag() {
    cleanupDragState();
    clearSelection();
}

function createPieceElement(position) {
    const pieceKey = `${position.type}_${position.color}`;
    const pieceImage = document.createElement('img');
    const fileName = pieceFileNames[pieceKey] || `${pieceKey}.png`;

    pieceImage.src = `/static/games/pieces/${fileName}`;
    pieceImage.alt = pieceKey;
    pieceImage.draggable = false;
    pieceImage.classList.add('piece');

    pieceImage.onerror = function () {
        const fallback = document.createElement('span');
        fallback.classList.add('piece-fallback');
        fallback.innerText = pieceFallbacks[pieceKey] || '?';

        pieceImage.replaceWith(fallback);
    };

    return pieceImage;
}

updateTurnIndicator();

function setupSquareInteraction(square) {
    square.addEventListener('pointerdown', function (event) {
        if (event.button !== 0) {
            return;
        }

        startPieceDrag(square, event);
    });

    square.addEventListener('click', async function () {
        if (suppressNextClick) {
            suppressNextClick = false;
            if (!promotionPending && isViewingLatestPosition() && !gameOver && canPlayerMoveFrom(square)) {
                clearSelection();
                selectSquare(square);
            }
            return;
        }

        if (promotionPending) {
            return;
        }

        if (canQueueMoveFrom(square) || (selectedSquare && canQueueMoveFrom(selectedSquare))) {
            if (queuedMove) {
                clearQueuedMove();
                clearSelection();
                return;
            }

            if (selectedSquare === null) {
                selectSquare(square);
                return;
            }

            if (selectedSquare === square) {
                clearSelection();
                return;
            }

            if (isPossibleMove(square)) {
                queueMove(selectedSquare, square);
                return;
            }

            clearSelection();

            if (canQueueMoveFrom(square)) {
                selectSquare(square);
            }

            return;
        }

        if (queuedMove) {
            clearQueuedMove();
        }

        if (!isViewingLatestPosition() || gameOver) {
            if (!analysisMode) {
                clearSelection();
                return;
            }
        }

        if (selectedSquare === null) {
            if (canPlayerMoveFrom(square)) {
                selectSquare(square);
            }

            return;
        }

        if (selectedSquare === square) {
            clearSelection();
            return;
        }

        if (sameColor(selectedSquare, square)) {
            clearSelection();

            if (canPlayerMoveFrom(square)) {
                selectSquare(square);
            }

            return;
        }

        if (!isPossibleMove(square)) {
            return;
        }

        if (analysisMode) {
            await playAnalysisMove(selectedSquare, square);
        } else {
            await playMove(selectedSquare, square);
        }
    });
}

function createLegacySquare(row, col) {
    const square = document.createElement('div');
    const coord = letters[col] + row;

    square.classList.add('square');
    square.dataset.coord = coord;

    const isLight = (row + col) % 2 === 0;
    square.classList.add(isLight ? 'square-light' : 'square-dark');

    const position = initialPosition[coord];

    square.style.backgroundColor = isLight ? '#f0d9b5' : '#b58863';

    if (position) {
        square.appendChild(createPieceElement(position));
        square.dataset.color = position.color;
        square.dataset.type = position.type;
    } else {
        square.dataset.color = '';
        square.dataset.type = '';
    }

    return square;
}

function setupBoardSquares() {
    let squares = Array.from(board.querySelectorAll('.square'));

    if (squares.length !== 64) {
        board.replaceChildren();

        for (let row = 8; row >= 1; row--) {
            for (let col = 0; col < 8; col++) {
                board.appendChild(createLegacySquare(row, col));
            }
        }

        squares = Array.from(board.querySelectorAll('.square'));
        board.dataset.renderer = 'legacy';
    }

    squares.forEach(setupSquareInteraction);
}

setupBoardSquares();

moveSound = buildSound(typeof MOVE_SOUND_URL !== 'undefined' ? MOVE_SOUND_URL : null, 1);
startSound = buildSound(typeof START_SOUND_URL !== 'undefined' ? START_SOUND_URL : null, 1);
preloadSoundBuffer(typeof MOVE_SOUND_URL !== 'undefined' ? MOVE_SOUND_URL : null).then((buffer) => {
    moveSoundBuffer = buffer;
});
preloadSoundBuffer(typeof START_SOUND_URL !== 'undefined' ? START_SOUND_URL : null).then((buffer) => {
    startSoundBuffer = buffer;
});

if (isMultiplayerMode() && SAVED_MOVES.length === 0 && typeof GAME_ID !== 'undefined' && GAME_ID) {
    const startSoundKey = `gchess-start-sound-${GAME_ID}`;

    try {
        if (window.sessionStorage.getItem(startSoundKey) !== 'played') {
            window.sessionStorage.setItem(startSoundKey, 'played');
            playStartSound();
        }
    } catch (error) {
        playStartSound();
    }
}

restoreComputerGameState();
updateBoardOrientation();
renderSavedMoveList();
loadPositionUntil(SAVED_MOVES.length);
updateCapturedMaterial();
renderClock();
renderDrawOffer();

if (
    typeof GAME_STATUS !== 'undefined' &&
    GAME_STATUS === 'finished' &&
    typeof GAME_RESULT !== 'undefined'
) {
    gameOver = true;

    if (GAME_RESULT === 'white' || GAME_RESULT === 'black') {
        showGameStatus(GAME_RESULT === 'white' ? uiText('white_wins', 'VitÃ³ria das brancas') : uiText('black_wins', 'VitÃ³ria das pretas'));
    } else if (GAME_RESULT === 'draw') {
        showGameStatus(uiText('game_drawn', 'Partida empatada'));
    } else {
        updateFinishedPanelState();
    }

    renderDrawOffer();
    updateTurnIndicator();
}

if (clockIsEnabled()) {
    setInterval(renderClock, 1000);
}

if (isMultiplayerMode() && !gameStatePollingId) {
    pollingLog('polling iniciado', {
        gameId: typeof GAME_ID !== 'undefined' ? GAME_ID : null,
        intervalMs: GAME_STATE_POLL_INTERVAL_MS,
        moveCount: SAVED_MOVES.length,
        lastMoveId: lastKnownMoveId(),
        currentTurn: currentTurn,
        playerColor: playerColor(),
    });
    startGameStatePolling();
    connectGameSocket();
}

if (gameChatToggle && typeof GAME_ID !== 'undefined' && GAME_ID && !gameChatPollingId) {
    startGameChatPolling();
}

function clockIsEnabled() {
    return Boolean(gameClock && gameClock.enabled);
}

function secondsSinceClockStart() {
    if (!clockIsEnabled() || !gameClock.started_at || !gameClock.server_now) {
        return 0;
    }

    const serverStartedAt = new Date(gameClock.started_at).getTime();
    const serverNow = new Date(gameClock.server_now).getTime();
    const localNow = Date.now();

    if (Number.isNaN(serverStartedAt) || Number.isNaN(serverNow)) {
        return 0;
    }

    return Math.max(0, Math.floor((localNow - serverNow + serverNow - serverStartedAt) / 1000));
}

function liveClockSeconds(color) {
    if (!clockIsEnabled()) {
        return null;
    }

    const baseSeconds = color === 'white'
        ? gameClock.white_seconds
        : gameClock.black_seconds;

    if (gameOver || gameClock.status === 'finished' || gameClock.active_color !== color) {
        return Math.max(0, baseSeconds || 0);
    }

    return Math.max(0, (baseSeconds || 0) - secondsSinceClockStart());
}

function formatClock(seconds) {
    seconds = Math.max(0, Math.ceil(seconds || 0));

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

function applyClockState(clock) {
    if (!clock) {
        return;
    }

    gameClock = clock;

    if (clock.status === 'finished') {
        gameOver = true;
        finishedGameSynced = true;

        if (clock.result === 'white' || clock.result === 'black') {
            showGameStatus(clock.result === 'white' ? uiText('white_wins', 'Vitória das brancas') : uiText('black_wins', 'Vitória das pretas'));
        } else if (clock.result === 'draw') {
            showGameStatus(uiText('game_drawn', 'Partida empatada'));
        }
    }

    renderClock();
}

function showServerGameResult(data) {
    if (!data || !data.game_finished) {
        return;
    }

    gameOver = true;
    renderDrawOffer();
    hideResignConfirmPanel();

    if (offerDrawButton) {
        offerDrawButton.disabled = true;
    }

    if (resignButton) {
        resignButton.disabled = true;
    }

    if (data.result === 'draw') {
        showGameStatus(uiText('game_drawn', 'Partida empatada'));
        updateTurnIndicator();
        return;
    }

    if (data.winner === 'white' || data.winner === 'black') {
        showGameStatus(data.winner === 'white' ? uiText('white_wins', 'Vitória das brancas') : uiText('black_wins', 'Vitória das pretas'));
        updateTurnIndicator();
    }
}

function applyDrawOfferState(offer) {
    if (!offer) {
        return;
    }

    drawOffer = offer;
    renderDrawOffer();
}

function renderDrawOffer() {
    updateFinishedPanelState();

    if (!drawOfferPanel || !drawOfferText) {
        return;
    }

    if (offerDrawButton) {
        offerDrawButton.disabled = gameOver || Boolean(drawOffer && drawOffer.pending && !drawOffer.can_accept);
    }

    if (resignButton) {
        resignButton.disabled = gameOver;
    }

    if (!drawOffer || !drawOffer.pending || gameOver) {
        drawOfferPanel.hidden = true;
        return;
    }

    drawOfferPanel.hidden = false;

    if (drawOffer.can_accept) {
        drawOfferText.innerText = uiText('draw_offer_received', 'Seu oponente ofereceu empate.');
        if (drawOfferActions) {
            drawOfferActions.hidden = false;
        }
    } else {
        drawOfferText.innerText = uiText('draw_offer_sent', 'Oferta de empate enviada. Aguardando resposta.');
        if (drawOfferActions) {
            drawOfferActions.hidden = true;
        }
    }
}

function showResignConfirmPanel() {
    if (!resignConfirmPanel || gameOver) {
        return;
    }

    resignConfirmPanel.hidden = false;
}

function hideResignConfirmPanel() {
    if (resignConfirmPanel) {
        resignConfirmPanel.hidden = true;
    }
}

async function postGameAction(url, payload = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || 'A ação não pôde ser concluída.');
    }

    applyClockState(data.clock);
    applyDrawOfferState(data.draw_offer);
    showServerGameResult(data);

    return data;
}

function renderGameChat(data) {
    if (!gameChatMessages || !gameChatCount) {
        return;
    }

    gameChatMessages.replaceChildren();

    if (!data.messages || data.messages.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'game-chat-empty';
        empty.innerText = uiText('no_chat_messages', 'Nenhuma mensagem ainda.');
        gameChatMessages.appendChild(empty);
    } else {
        data.messages.forEach(function (message) {
            const item = document.createElement('div');
            item.className = message.mine ? 'game-chat-message game-chat-message-mine' : 'game-chat-message';
            item.dataset.messageId = message.id;

            const meta = document.createElement('span');
            meta.className = 'game-chat-meta';
            meta.innerText = `${message.sender} · ${message.created_at}`;

            const text = document.createElement('p');
            text.innerText = message.text;

            item.append(meta, text);
            gameChatMessages.appendChild(item);
        });
    }

    gameChatMessages.scrollTop = gameChatMessages.scrollHeight;

    const unreadCount = data.unread_count || 0;
    gameChatCount.innerText = unreadCount;
    gameChatCount.hidden = gameChatOpen || unreadCount === 0;
}

function appendGameChatMessage(message) {
    if (!gameChatMessages || !gameChatCount) {
        return;
    }

    if (gameChatMessages.querySelector(`[data-message-id="${message.id}"]`)) {
        return;
    }

    const empty = gameChatMessages.querySelector('.game-chat-empty');
    if (empty) {
        empty.remove();
    }

    const item = document.createElement('div');
    const mine = message.mine || message.sender_id === currentUserId();
    item.className = mine ? 'game-chat-message game-chat-message-mine' : 'game-chat-message';
    item.dataset.messageId = message.id;

    const meta = document.createElement('span');
    meta.className = 'game-chat-meta';
    meta.innerText = `${message.sender} - ${message.created_at}`;

    const text = document.createElement('p');
    text.innerText = message.text;

    item.append(meta, text);
    gameChatMessages.appendChild(item);
    gameChatMessages.scrollTop = gameChatMessages.scrollHeight;

    if (gameChatOpen) {
        fetchGameChat();
        return;
    }

    if (!mine) {
        const unreadCount = Number(gameChatCount.innerText || '0') + 1;
        gameChatCount.innerText = unreadCount;
        gameChatCount.hidden = unreadCount === 0;
    }
}

async function fetchGameChat() {
    if (!GAME_ID || gameChatLoading) {
        return;
    }

    gameChatLoading = true;

    try {
        const markRead = gameChatOpen ? '?mark_read=1' : '';
        const response = await fetch(`/games/${GAME_ID}/chat/${markRead}`, {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache',
            },
        });

        if (shouldStopPollingForAuth(response)) {
            // Stop polling after login redirects so logged-out tabs do not spam Django.
            stopGameChatPolling('Chat polling detenido: la sesiÃ³n parece haber expirado.');
            return;
        }

        if (!response.ok) {
            if (!gameChatNetworkWarningShown) {
                console.warn('No se pudo actualizar el chat:', response.status, response.statusText);
                gameChatNetworkWarningShown = true;
            }
            return;
        }

        gameChatNetworkWarningShown = false;
        const data = await response.json();
        renderGameChat(data);
    } catch (error) {
        if (!gameChatNetworkWarningShown) {
            console.warn('No se pudo actualizar el chat:', error);
            gameChatNetworkWarningShown = true;
        }
    } finally {
        gameChatLoading = false;
    }
}

function toggleGameChat() {
    if (!gameChatPanel) {
        return;
    }

    gameChatOpen = !gameChatOpen;
    gameChatPanel.hidden = !gameChatOpen;

    if (!gameChatOpen && gameChatEmojiPanel) {
        gameChatEmojiPanel.hidden = true;
    }

    if (gameChatOpen) {
        fetchGameChat();
        if (gameChatInput) {
            gameChatInput.focus();
        }
    }
}

function closeGameChat() {
    if (!gameChatPanel) {
        return;
    }

    gameChatOpen = false;
    gameChatPanel.hidden = true;

    if (gameChatEmojiPanel) {
        gameChatEmojiPanel.hidden = true;
    }
}

function insertGameChatEmoji(emoji) {
    if (!gameChatInput) {
        return;
    }

    const start = gameChatInput.selectionStart || gameChatInput.value.length;
    const end = gameChatInput.selectionEnd || gameChatInput.value.length;
    const before = gameChatInput.value.slice(0, start);
    const after = gameChatInput.value.slice(end);

    gameChatInput.value = `${before}${emoji}${after}`;
    gameChatInput.focus();
    gameChatInput.selectionStart = start + emoji.length;
    gameChatInput.selectionEnd = start + emoji.length;
}

function renderClock() {
    if (!clockIsEnabled() || !whiteClock || !blackClock) {
        return;
    }

    const whiteSeconds = liveClockSeconds('white');
    const blackSeconds = liveClockSeconds('black');

    whiteClock.innerText = formatClock(whiteSeconds);
    blackClock.innerText = formatClock(blackSeconds);

    document.querySelectorAll('.clock-row').forEach(row => {
        const color = row.dataset.clockColor;
        const seconds = color === 'white' ? whiteSeconds : blackSeconds;
        row.classList.toggle('active', !gameOver && gameClock.active_color === color);
        row.classList.toggle('flagged', seconds <= 0);
    });

    if (!gameOver && gameClock.status !== 'finished') {
        if (whiteSeconds <= 0) {
            finishByTimeout('white');
        } else if (blackSeconds <= 0) {
            finishByTimeout('black');
        }
    }
}

function finishByTimeout(loser) {
    if (timeoutSyncInProgress || gameOver) {
        return;
    }

    const winner = loser === 'white' ? 'black' : 'white';
    timeoutSyncInProgress = true;
    gameOver = true;
    clearSelection();
    showGameStatus(loser === 'white' ? 'Tempo das brancas esgotado' : 'Tempo das pretas esgotado');
    updateTurnIndicator();

    syncFinishedGame(winner, {
        reason: 'timeout',
        loser: loser,
    });
}

function coordToPosition(coord) {
    const file = coord[0];
    const rank = parseInt(coord[1]);

    return {
        col: letters.indexOf(file),
        row: rank
    };
}

function positionToCoord(col, row) {
    if (col < 0 || col > 7 || row < 1 || row > 8) {
        return null;
    }

    return letters[col] + row;
}

function getHorseMoves(square) {
    const { col, row } = coordToPosition(square.dataset.coord);

    const moves = [
        [1, 2], [2, 1],
        [2, -1], [1, -2],
        [-1, -2], [-2, -1],
        [-2, 1], [-1, 2],
    ];

    return moves
        .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
        .filter(coord => coord !== null);
}


function getPawnMoves(square) {
    const moves = [];

    const { col, row } = coordToPosition(square.dataset.coord);
    const color = square.dataset.color;

    const direction = color === 'white' ? 1 : -1;
    const startRow = color === 'white' ? 2 : 7;
    const enPassantRow = color === 'white' ? 5 : 4;

    // 1 casa para frente
    const frontCoord = positionToCoord(col, row + direction);

    if (frontCoord) {
        const frontSquare = document.querySelector(`[data-coord="${frontCoord}"]`);

        if (frontSquare.dataset.color === '') {
            moves.push(frontCoord);

            // 2 casas para frente desde a posição inicial
            const doubleFrontCoord = positionToCoord(col, row + direction * 2);

            if (row === startRow && doubleFrontCoord) {
                const doubleFrontSquare = document.querySelector(`[data-coord="${doubleFrontCoord}"]`);

                if (doubleFrontSquare.dataset.color === '') {
                    moves.push(doubleFrontCoord);
                }
            }
        }
    }

    // capturas diagonales normales
    const captureCoords = [
        positionToCoord(col - 1, row + direction),
        positionToCoord(col + 1, row + direction),
    ];

    captureCoords.forEach(coord => {
        if (!coord) return;

        const targetSquare = document.querySelector(`[data-coord="${coord}"]`);

        if (
            targetSquare.dataset.color !== '' &&
            targetSquare.dataset.color !== color
        ) {
            moves.push(coord);
        }
    });

    // comer al paso
    if (row === enPassantRow && lastMove !== null) {
        const lastFrom = coordToPosition(lastMove.from);
        const lastTo = coordToPosition(lastMove.to);

        const enemyPawnMovedTwo =
            lastMove.piece_type === 'pawn' &&
            lastMove.piece_color !== color &&
            Math.abs(lastTo.row - lastFrom.row) === 2;

        const enemyPawnIsBeside =
            lastTo.row === row &&
            Math.abs(lastTo.col - col) === 1;

        if (enemyPawnMovedTwo && enemyPawnIsBeside) {
            const enPassantCoord = positionToCoord(lastTo.col, row + direction);
            moves.push(enPassantCoord);
        }
    }

    return moves;
}

function getPremovePawnMoves(square) {
    const moves = [];
    const { col, row } = coordToPosition(square.dataset.coord);
    const color = square.dataset.color;
    const direction = color === 'white' ? 1 : -1;
    const startRow = color === 'white' ? 2 : 7;
    const frontCoord = positionToCoord(col, row + direction);

    if (frontCoord) {
        const frontSquare = getSquare(frontCoord);

        if (frontSquare && frontSquare.dataset.color === '') {
            moves.push(frontCoord);

            const doubleFrontCoord = positionToCoord(col, row + direction * 2);

            if (row === startRow && doubleFrontCoord) {
                const doubleFrontSquare = getSquare(doubleFrontCoord);

                if (doubleFrontSquare && doubleFrontSquare.dataset.color === '') {
                    moves.push(doubleFrontCoord);
                }
            }
        }
    }

    [
        positionToCoord(col - 1, row + direction),
        positionToCoord(col + 1, row + direction),
    ].forEach(coord => {
        if (coord) {
            moves.push(coord);
        }
    });

    return moves;
}

function getPremoveSlidingMoves(square, directions) {
    const moves = [];
    const { col, row } = coordToPosition(square.dataset.coord);

    directions.forEach(([dc, dr]) => {
        let nextCol = col + dc;
        let nextRow = row + dr;

        while (true) {
            const coord = positionToCoord(nextCol, nextRow);

            if (coord === null) {
                break;
            }

            const targetSquare = getSquare(coord);
            moves.push(coord);

            if (targetSquare.dataset.color !== '') {
                break;
            }

            nextCol += dc;
            nextRow += dr;
        }
    });

    return moves;
}

function getPremoveMoves(square) {
    const type = square.dataset.type;

    if (type === 'pawn') {
        return getPremovePawnMoves(square);
    }

    if (type === 'horse') {
        return getHorseMoves(square);
    }

    if (type === 'bishop') {
        return getPremoveSlidingMoves(square, [
            [1, 1],
            [1, -1],
            [-1, -1],
            [-1, 1],
        ]);
    }

    if (type === 'rook') {
        return getPremoveSlidingMoves(square, [
            [0, 1],
            [1, 0],
            [0, -1],
            [-1, 0],
        ]);
    }

    if (type === 'queen') {
        return getPremoveSlidingMoves(square, [
            [0, 1],
            [1, 1],
            [1, 0],
            [1, -1],
            [0, -1],
            [-1, -1],
            [-1, 0],
            [-1, 1],
        ]);
    }

    if (type === 'king') {
        const { col, row } = coordToPosition(square.dataset.coord);

        return [
            [0, 1],
            [1, 1],
            [1, 0],
            [1, -1],
            [0, -1],
            [-1, -1],
            [-1, 0],
            [-1, 1],
        ]
            .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
            .filter(coord => coord !== null);
    }

    return [];
}

function highlightMoves(coords, options = {}) {
    coords.forEach(coord => {
        const square = document.querySelector(`[data-coord="${coord}"]`);

        if (square && (options.allowOwnPieces || !sameColor(selectedSquare, square)) && !isKingSquare(square)) {
            square.classList.add('possible-move');
        }
    });
}

function isPossibleMove(square) {
    return square.classList.contains('possible-move');
}

function getRow(coord) {
    return Number(coord[1]);
}

function getCol(coord) {
    return letters.indexOf(coord[0]);
}

function isValidPawnMove(piece, from, to, targetPiece) {
    const fromRow = getRow(from);
    const toRow = getRow(to);
    const fromCol = getCol(from);
    const toCol = getCol(to);

    const direction = isWhitePiece(piece) ? 1 : -1;
    const startRow = isWhitePiece(piece) ? 2 : 7;

    const rowDiff = toRow - fromRow;
    const colDiff = Math.abs(toCol - fromCol);

    // mover 1 casa para frente
    if (fromCol === toCol && targetPiece === '') {
        if (rowDiff === direction) {
            return true;
        }

        // mover 2 casas desde a posição inicial
        if (fromRow === startRow && rowDiff === direction * 2) {
            return true;
        }
    }

    // capturar diagonal
    if (colDiff === 1 && targetPiece !== '') {
        return rowDiff === direction;
    }

    return false;
}

function isValidRookMove(from, to) {
    const fromRow = getRow(from);
    const toRow = getRow(to);
    const fromCol = getCol(from);
    const toCol = getCol(to);

    return fromRow === toRow || fromCol === toCol;
}

function getPossibleMoves(square) {
    const type = square.dataset.type;

    if (type === 'horse') {
        return getHorseMoves(square);
    }

    if (type === 'pawn') {
        return getPawnMoves(square);
    }

    if (type === 'rook') {
        return getRookMoves(square);
    }

    if (type === 'bishop') {
        return getBishopMoves(square);
    }

    if (type === 'queen') {
        return getQueenMoves(square);
    }

    if (type === 'king') {
        return getKingMoves(square);
    }

    return [];
}

function getLegalMoves(square) {
    if (analysisMode) {
        return getPossibleMoves(square).filter(coord => {
            const targetSquare = getSquare(coord);
            return targetSquare && !sameColor(square, targetSquare) && !isKingSquare(targetSquare);
        });
    }

    return getPossibleMoves(square).filter(coord => isLegalMove(square, getSquare(coord)));
}

function isLegalMove(fromSquare, toSquare) {
    if (!toSquare || sameColor(fromSquare, toSquare) || isKingSquare(toSquare)) {
        return false;
    }

    const movingColor = fromSquare.dataset.color;
    const boardState = snapshotBoard();

    applyMoveForValidation(fromSquare, toSquare);

    const kingCoord = findKingCoord(movingColor);
    const isLegal = kingCoord !== null && !isSquareAttacked(kingCoord, getEnemyColor(movingColor));

    restoreBoard(boardState);

    return isLegal;
}

function snapshotBoard() {
    return Array.from(document.querySelectorAll('.square')).map(square => ({
        square: square,
        color: square.dataset.color,
        type: square.dataset.type,
        children: Array.from(square.childNodes),
    }));
}

function restoreBoard(boardState) {
    boardState.forEach(state => {
        state.square.replaceChildren(...state.children);
        state.square.dataset.color = state.color;
        state.square.dataset.type = state.type;
    });
}

function applyMoveForValidation(fromSquare, toSquare) {
    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;
    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;

    if (
        movingType === 'pawn' &&
        from[0] !== to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnSquare = getSquare(to[0] + from[1]);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
}

function findKingCoord(color) {
    const kingSquare = Array.from(document.querySelectorAll('.square')).find(square => {
        return square.dataset.type === 'king' && square.dataset.color === color;
    });

    return kingSquare ? kingSquare.dataset.coord : null;
}

function isKingInCheck(color) {
    const kingCoord = findKingCoord(color);

    return kingCoord !== null && isSquareAttacked(kingCoord, getEnemyColor(color));
}

function hasAnyLegalMove(color) {
    const pieces = Array.from(document.querySelectorAll('.square')).filter(square => {
        return square.dataset.color === color;
    });

    return pieces.some(square => getLegalMoves(square).length > 0);
}

function isCheckmate(color) {
    return isKingInCheck(color) && !hasAnyLegalMove(color);
}

function isStalemate(color) {
    return !isKingInCheck(color) && !hasAnyLegalMove(color);
}

function bishopSquareColor(coord) {
    return (getCol(coord) + getRow(coord)) % 2;
}

function currentNonKingPieces() {
    return Array.from(document.querySelectorAll('.square'))
        .filter(square => square.dataset.color && square.dataset.type && square.dataset.type !== 'king')
        .map(square => ({
            type: square.dataset.type,
            color: square.dataset.color,
            coord: square.dataset.coord,
        }));
}

function hasInsufficientMaterial() {
    const pieces = currentNonKingPieces();

    if (pieces.length === 0) {
        return true;
    }

    if (pieces.length === 1 && ['bishop', 'horse'].includes(pieces[0].type)) {
        return true;
    }

    if (pieces.length === 2 && pieces.every(piece => piece.type === 'bishop')) {
        return bishopSquareColor(pieces[0].coord) === bishopSquareColor(pieces[1].coord);
    }

    return false;
}

function checkGameEnd() {
    if (analysisMode) {
        return null;
    }

    if (isCheckmate(currentTurn)) {
        gameOver = true;
        clearSelection();
        showGameStatus('xeque-mate!');
        updateTurnIndicator();
        return {
            result: getEnemyColor(currentTurn),
            winner: getEnemyColor(currentTurn),
        };
    }

    if (isStalemate(currentTurn)) {
        gameOver = true;
        clearSelection();
        showGameStatus('Partida empatada por ahogado');
        updateTurnIndicator();
        return {
            result: 'draw',
            winner: null,
        };
    }

    if (hasInsufficientMaterial()) {
        gameOver = true;
        clearSelection();
        showGameStatus('Partida empatada por material insuficiente');
        updateTurnIndicator();
        return {
            result: 'draw',
            winner: null,
        };
    }

    return null;
}

function refreshGameStatus() {
    if (analysisMode) {
        hideGameStatus();
        return;
    }

    gameOver = isViewingLatestPosition() && (isCheckmate(currentTurn) || isStalemate(currentTurn) || hasInsufficientMaterial());

    if (gameOver && isCheckmate(currentTurn)) {
        showGameStatus('xeque-mate!');
        syncFinishedGame(getEnemyColor(currentTurn));
    } else if (gameOver && isStalemate(currentTurn)) {
        showGameStatus('Partida empatada por ahogado');
        syncFinishedGame(null, { result: 'draw' });
    } else if (gameOver && hasInsufficientMaterial()) {
        showGameStatus('Partida empatada por material insuficiente');
        syncFinishedGame(null, { result: 'draw' });
    } else {
        hideGameStatus();
    }
}

function getSlidingMoves(square, directions) {
    const moves = [];
    const { col, row } = coordToPosition(square.dataset.coord);

    directions.forEach(([dc, dr]) => {
        let nextCol = col + dc;
        let nextRow = row + dr;

        while (true) {
            const coord = positionToCoord(nextCol, nextRow);

            if (coord === null) {
                break;
            }

            const targetSquare = document.querySelector(`[data-coord="${coord}"]`);

            if (targetSquare.dataset.color === '') {
                moves.push(coord);
            } else {
                if (!sameColor(square, targetSquare)) {
                    moves.push(coord);
                }

                break;
            }

            nextCol += dc;
            nextRow += dr;
        }
    });

    return moves;
}

function getRookMoves(square) {
    return getSlidingMoves(square, [
        [0, 1],
        [1, 0],
        [0, -1],
        [-1, 0],
    ]);
}

function getBishopMoves(square) {
    return getSlidingMoves(square, [
        [1, 1],
        [1, -1],
        [-1, -1],
        [-1, 1],
    ]);
}

function getQueenMoves(square) {
    return getSlidingMoves(square, [
        [0, 1],
        [1, 0],
        [0, -1],
        [-1, 0],
        [1, 1],
        [1, -1],
        [-1, -1],
        [-1, 1],
    ]);
}

function getKingMoves(square) {
    const { col, row } = coordToPosition(square.dataset.coord);
    const color = square.dataset.color;

    const moves = [
        [0, 1],
        [1, 1],
        [1, 0],
        [1, -1],
        [0, -1],
        [-1, -1],
        [-1, 0],
        [-1, 1],
    ]
        .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
        .filter(coord => coord !== null);

    return moves.concat(getCastlingMoves(square));
}

function getSquare(coord) {
    return document.querySelector(`[data-coord="${coord}"]`);
}

function getEnemyColor(color) {
    return color === 'white' ? 'black' : 'white';
}

function isSquareAttacked(coord, byColor) {
    const squares = document.querySelectorAll('.square');

    for (const square of squares) {
        if (square.dataset.color !== byColor) {
            continue;
        }

        const attackedCoords = getAttackedSquares(square);

        if (attackedCoords.includes(coord)) {
            return true;
        }
    }

    return false;
}

function getAttackedSquares(square) {
    const type = square.dataset.type;
    const color = square.dataset.color;
    const { col, row } = coordToPosition(square.dataset.coord);

    if (type === 'pawn') {
        const direction = color === 'white' ? 1 : -1;

        return [
            positionToCoord(col - 1, row + direction),
            positionToCoord(col + 1, row + direction),
        ].filter(coord => coord !== null);
    }

    if (type === 'horse') {
        return getHorseMoves(square);
    }

    if (type === 'bishop') {
        return getBishopMoves(square);
    }

    if (type === 'rook') {
        return getRookMoves(square);
    }

    if (type === 'queen') {
        return getQueenMoves(square);
    }

    if (type === 'king') {
        const moves = [
            [0, 1],
            [1, 1],
            [1, 0],
            [1, -1],
            [0, -1],
            [-1, -1],
            [-1, 0],
            [-1, 1],
        ];

        return moves
            .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
            .filter(coord => coord !== null);
    }

    return [];
}

function getCastlingMoves(square) {
    const moves = [];
    const color = square.dataset.color;
    const enemyColor = getEnemyColor(color);

    const kingStart = color === 'white' ? 'e1' : 'e8';
    const row = color === 'white' ? '1' : '8';

    if (square.dataset.coord !== kingStart) {
        return moves;
    }

    if (castlingRights[color].kingMoved) {
        return moves;
    }

    if (isSquareAttacked(kingStart, enemyColor)) {
        return moves;
    }

    // Roque curto: rei para a direita
    const shortRookCoord = `h${row}`;
    const shortRook = getSquare(shortRookCoord);

    if (
        !castlingRights[color].rightRookMoved &&
        shortRook.dataset.type === 'rook' &&
        shortRook.dataset.color === color &&
        getSquare(`f${row}`).dataset.color === '' &&
        getSquare(`g${row}`).dataset.color === '' &&
        !isSquareAttacked(`f${row}`, enemyColor) &&
        !isSquareAttacked(`g${row}`, enemyColor)
    ) {
        moves.push(`g${row}`);
    }

    // Roque longo: rei para a esquerda
    const longRookCoord = `a${row}`;
    const longRook = getSquare(longRookCoord);

    if (
        !castlingRights[color].leftRookMoved &&
        longRook.dataset.type === 'rook' &&
        longRook.dataset.color === color &&
        getSquare(`b${row}`).dataset.color === '' &&
        getSquare(`c${row}`).dataset.color === '' &&
        getSquare(`d${row}`).dataset.color === '' &&
        !isSquareAttacked(`d${row}`, enemyColor) &&
        !isSquareAttacked(`c${row}`, enemyColor)
    ) {
        moves.push(`c${row}`);
    }

    return moves;
}

function getCSRFToken() {
    const cookies = document.cookie.split(';');

    for (let cookie of cookies) {
        cookie = cookie.trim();

        if (cookie.startsWith('csrftoken=')) {
            return cookie.substring('csrftoken='.length);
        }
    }

    return '';
}

function saveMoveToDatabase(moveData, gameState = {}) {
    if (typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE) {
        return;
    }
    if (isComputerMode()) {
        return;
    }

    const payload = {
        ...moveData,
        game_finished: Boolean(gameState.finished),
        winner: gameState.winner,
        result: gameState.result,
    };

    if (sendGameSocketMessage({ type: 'move.create', move: payload })) {
        pendingMoveSaveCount += 1;
        return;
    }

    pendingMoveSaveCount += 1;

    fetch(`/games/${GAME_ID}/save-move/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify(payload),
    })
    .then(response => {
        if (!response.ok) {
            syncMovesFromServer();
            throw new Error('Movimento recusado pelo servidor.');
        }

        return response.json();
    })
    .then(data => {
        console.log('Movimento salvo:', data);
        if (data.move_id) {
            const savedMove = SAVED_MOVES.find(move =>
                !move.id &&
                move.move_number === moveData.move_number &&
                move.from === moveData.from &&
                move.to === moveData.to
            );

            if (savedMove) {
                savedMove.id = data.move_id;
            }
        }
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);
    })
    .catch(error => {
        console.error('Erro ao salvar movimento:', error);
    })
    .finally(() => {
        pendingMoveSaveCount = Math.max(0, pendingMoveSaveCount - 1);
    });
}

function syncFinishedGame(winner, options = {}) {
    if (
        finishedGameSynced ||
        typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE ||
        isComputerMode()
    ) {
        return;
    }

    finishedGameSynced = true;

    fetch(`/games/${GAME_ID}/mark-finished/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify({
            winner: winner,
            reason: options.reason || null,
            loser: options.loser || null,
            result: options.result || null,
        }),
    })
    .then(response => response.ok ? response.json() : Promise.reject(response))
    .then(data => {
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);
    })
    .catch(error => {
        finishedGameSynced = false;
        timeoutSyncInProgress = false;
        console.error('Erro ao finalizar partida:', error);
    });
}

function clearBoard() {
    document.querySelectorAll('.square').forEach(square => {
        square.replaceChildren();
        square.dataset.color = '';
        square.dataset.type = '';
    });
}

function setupInitialPosition() {
    clearBoard();

    Object.entries(initialPosition).forEach(([coord, position]) => {
        const square = getSquare(coord);

        square.appendChild(createPieceElement(position));
        square.dataset.color = position.color;
        square.dataset.type = position.type;
    });
}

async function applyMoveWithoutSaving(move, shouldAnimate = false) {
    const promotionType = move.promotion || 'queen';
    const fromSquare = getSquare(move.from);
    const toSquare = getSquare(move.to);
    const movingType = move.piece_type;
    const movingColor = move.piece_color;

    if (shouldAnimate) {
        await animateMove(fromSquare, toSquare);
    }

    if (
        movingType === 'pawn' &&
        move.from[0] !== move.to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnCoord = move.to[0] + move.from[1];
        const capturedPawnSquare = getSquare(capturedPawnCoord);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(move.from) - getCol(move.to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (move.to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (move.to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
    // promoção automática
    if (isPromotionMove(movingType, movingColor, move.to)) {
        promotePawn(toSquare, movingColor, promotionType);
    }

    updateCastlingRightsAfterMove(move);
}

async function applyAppendedServerMoves(newMoves, oldMoveCount) {
    for (let index = oldMoveCount; index < newMoves.length; index++) {
        const move = newMoves[index];

        await applyMoveWithoutSaving(move, true);
        lastMove = move;
        historyIndex = index + 1;
        moveNumber = historyIndex + 1;
        currentTurn = historyIndex % 2 === 0 ? 'white' : 'black';
    }

    refreshGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function loadPositionUntil(index) {
    index = Math.max(0, Math.min(index, SAVED_MOVES.length));

    clearSelection();
    setupInitialPosition();
    resetCastlingRights();

    for (let i = 0; i < index; i++) {
        applyMoveWithoutSaving(SAVED_MOVES[i]);
    }

    historyIndex = index;
    moveNumber = SAVED_MOVES.length + 1;
    currentTurn = index % 2 === 0 ? 'white' : 'black';
    lastMove = index > 0 ? SAVED_MOVES[index - 1] : null;

    refreshGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
    saveComputerGameState();
    window.gchessHistoryIndex = historyIndex;
    window.gchessSavedMoveCount = SAVED_MOVES.length;
    updateAnalyzerCommentForPosition(historyIndex);
    document.dispatchEvent(new CustomEvent('gchess:position-changed', {
        detail: {
            historyIndex: historyIndex,
            moveCount: SAVED_MOVES.length,
        },
    }));
}

function updateAnalyzerCommentForPosition(index) {
    const analysisComment = document.getElementById('analysis-comment');

    if (!analysisComment || typeof MOVE_ANALYSIS === 'undefined' || !Array.isArray(MOVE_ANALYSIS)) {
        return;
    }

    if (index === 0) {
        analysisComment.innerText = analysisComment.dataset.initialComment || 'Posicao inicial.';
        return;
    }

    const data = MOVE_ANALYSIS[index - 1];
    analysisComment.innerText = data ? `${data.move_number}. ${data.comment}` : '';
}

function movesAreEqual(firstMove, secondMove) {
    return firstMove &&
        secondMove &&
        (!firstMove.id || !secondMove.id || firstMove.id === secondMove.id) &&
        firstMove.move_number === secondMove.move_number &&
        firstMove.from === secondMove.from &&
        firstMove.to === secondMove.to &&
        firstMove.piece_type === secondMove.piece_type &&
        firstMove.piece_color === secondMove.piece_color &&
        (firstMove.promotion || null) === (secondMove.promotion || null);
}

function updateLocalMoveIds(serverMoves) {
    serverMoves.forEach((serverMove, index) => {
        if (
            SAVED_MOVES[index] &&
            serverMove.id &&
            !SAVED_MOVES[index].id &&
            movesAreEqual(serverMove, SAVED_MOVES[index])
        ) {
            SAVED_MOVES[index].id = serverMove.id;
        }
    });
}

async function applyGameStateFromServer(data) {
    applyClockState(data.clock);
    applyDrawOfferState(data.draw_offer);
    showServerGameResult(data);

    if (data.game_finished) {
        gameOver = true;

        if (data.winner === 'white' || data.winner === 'black') {
            showGameStatus(data.winner === 'white' ? uiText('white_wins', 'Vitória das brancas') : uiText('black_wins', 'Vitória das pretas'));
        }
    }

    const serverMoves = data.moves || [];
    const oldMoveCount = SAVED_MOVES.length;
    if (pendingMoveSaveCount > 0 && serverMoves.length < oldMoveCount) {
        pollingLog('respuesta anterior ignorada mientras se guarda jugada local', {
            serverMoveCount: serverMoves.length,
            localMoveCount: oldMoveCount,
            pendingMoveSaveCount: pendingMoveSaveCount,
        });
        return;
    }

    const wasViewingLatestPosition = isViewingLatestPosition();
    const hasDifferentMoves = serverMoves.length !== SAVED_MOVES.length ||
        serverMoves.some((move, index) => !movesAreEqual(move, SAVED_MOVES[index]));

    if (!hasDifferentMoves) {
        updateLocalMoveIds(serverMoves);
        return;
    }

    pollingLog('movimiento nuevo detectado', {
        oldMoveCount: oldMoveCount,
        serverMoveCount: serverMoves.length,
        oldLastMoveId: lastKnownMoveId(),
        serverLastMoveId: data.last_move_id,
    });

    const hasOnlyAppendedMoves = serverMoves.length > oldMoveCount &&
        SAVED_MOVES.every((move, index) => movesAreEqual(move, serverMoves[index]));

    SAVED_MOVES.splice(0, SAVED_MOVES.length, ...serverMoves);
    renderSavedMoveList();

    if (hasOnlyAppendedMoves && wasViewingLatestPosition) {
        await applyAppendedServerMoves(serverMoves, oldMoveCount);
    } else {
        loadPositionUntil(SAVED_MOVES.length);
    }

    pollingLog('tablero actualizado', {
        moveCount: SAVED_MOVES.length,
        lastMoveId: lastKnownMoveId(),
        currentTurn: currentTurn,
        historyIndex: historyIndex,
    });

    if (serverMoves.length > oldMoveCount) {
        playMoveSound();
    }

    await playQueuedMoveIfReady();
}

async function syncMovesFromServer(options = {}) {
    if (
        typeof GAME_ID === 'undefined' ||
        typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE ||
        isComputerMode() ||
        promotionPending ||
        gameStateLoading
    ) {
        return;
    }

    gameStateLoading = true;
    pollingLog('request state', {
        gameId: GAME_ID,
        source: options.source || 'polling',
        moveCount: SAVED_MOVES.length,
        lastMoveId: lastKnownMoveId(),
        currentTurn: currentTurn,
        pendingMoveSaveCount: pendingMoveSaveCount,
    });

    try {
        const response = await fetch(`/games/${GAME_ID}/state/?_=${Date.now()}`, {
            cache: 'no-store',
            headers: {
                'Accept': 'application/json',
            },
        });

        if (shouldStopPollingForAuth(response)) {
            // Stop polling after login redirects so logged-out tabs do not spam Django.
            stopGameStatePolling('Polling de partida detenido: la sesiÃ³n parece haber expirado.');
            return;
        }

        if (!response.ok) {
            multiplayerSyncFailures += 1;
            if (!gameStateNetworkWarningShown) {
                console.warn('No se pudo actualizar el estado de la partida:', response.status, response.statusText);
                gameStateNetworkWarningShown = true;
            }
            return;
        }

        multiplayerSyncFailures = 0;
        gameStateNetworkWarningShown = false;
        const data = await response.json();
        pollingLog('respuesta endpoint', {
            gameId: data.game_id,
            moveCount: data.move_count,
            lastMoveId: data.last_move_id,
            turn: data.turn,
            fen: data.fen,
            version: data.version,
        });
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);

        if (data.game_finished) {
            gameOver = true;

            if (data.winner === 'white' || data.winner === 'black') {
                showGameStatus(data.winner === 'white' ? uiText('white_wins', 'Vitória das brancas') : uiText('black_wins', 'Vitória das pretas'));
            }
        }

        const serverMoves = data.moves || [];
        const oldMoveCount = SAVED_MOVES.length;
        if (pendingMoveSaveCount > 0 && serverMoves.length < oldMoveCount) {
            pollingLog('respuesta anterior ignorada mientras se guarda jugada local', {
                serverMoveCount: serverMoves.length,
                localMoveCount: oldMoveCount,
                pendingMoveSaveCount: pendingMoveSaveCount,
            });
            return;
        }

        const wasViewingLatestPosition = isViewingLatestPosition();
        const hasDifferentMoves = serverMoves.length !== SAVED_MOVES.length ||
            serverMoves.some((move, index) => !movesAreEqual(move, SAVED_MOVES[index]));

        if (!hasDifferentMoves) {
            return;
        }

        pollingLog('movimiento nuevo detectado', {
            oldMoveCount: oldMoveCount,
            serverMoveCount: serverMoves.length,
            oldLastMoveId: lastKnownMoveId(),
            serverLastMoveId: data.last_move_id,
        });

        const hasOnlyAppendedMoves = serverMoves.length > oldMoveCount &&
            SAVED_MOVES.every((move, index) => movesAreEqual(move, serverMoves[index]));

        SAVED_MOVES.splice(0, SAVED_MOVES.length, ...serverMoves);
        renderSavedMoveList();

        if (hasOnlyAppendedMoves && wasViewingLatestPosition) {
            await applyAppendedServerMoves(serverMoves, oldMoveCount);
        } else {
            loadPositionUntil(SAVED_MOVES.length);
        }

        pollingLog('tablero actualizado', {
            moveCount: SAVED_MOVES.length,
            lastMoveId: lastKnownMoveId(),
            currentTurn: currentTurn,
            historyIndex: historyIndex,
        });

        if (serverMoves.length > oldMoveCount) {
            playMoveSound();
        }

        await playQueuedMoveIfReady();
    } catch (error) {
        multiplayerSyncFailures += 1;
        if (!gameStateNetworkWarningShown) {
            console.warn('No se pudo sincronizar la partida:', error);
            gameStateNetworkWarningShown = true;
        }
    } finally {
        gameStateLoading = false;
    }
}

function startGameStatePolling() {
    if (!isMultiplayerMode() || gameStatePollingId) {
        return;
    }

    syncMovesFromServer();
    gameStatePollingId = setInterval(syncMovesFromServer, GAME_STATE_POLL_INTERVAL_MS);
    window.gchessGameStatePollingId = gameStatePollingId;
}

function pauseGameStatePolling() {
    if (gameStatePollingId) {
        clearInterval(gameStatePollingId);
        gameStatePollingId = null;
        window.gchessGameStatePollingId = null;
    }
}

function startGameChatPolling() {
    if (!gameChatToggle || typeof GAME_ID === 'undefined' || !GAME_ID || gameChatPollingId) {
        return;
    }

    fetchGameChat();
    gameChatPollingId = setInterval(fetchGameChat, 4000);
    window.gchessGameChatPollingId = gameChatPollingId;
}

function pauseGameChatPolling() {
    if (gameChatPollingId) {
        clearInterval(gameChatPollingId);
        gameChatPollingId = null;
        window.gchessGameChatPollingId = null;
    }
}

function gameSocketUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws/games/${GAME_ID}/`;
}

function nextGameSocketReconnectDelay() {
    const exponent = Math.max(0, gameSocketReconnectAttempts - 1);
    const backoff = Math.min(
        GAME_SOCKET_RECONNECT_BASE_MS * (2 ** exponent),
        GAME_SOCKET_RECONNECT_MAX_MS
    );
    const jitter = Math.floor(Math.random() * GAME_SOCKET_RECONNECT_JITTER_MS);

    return backoff + jitter;
}

function shouldReconnectGameSocket(event) {
    return !event || ![4001, 4003].includes(event.code);
}

function connectGameSocket() {
    if (
        !isMultiplayerMode() ||
        typeof GAME_ID === 'undefined' ||
        !GAME_ID ||
        typeof WebSocket === 'undefined' ||
        gameSocketConnected ||
        gameSocket && gameSocket.readyState === WebSocket.CONNECTING
    ) {
        return;
    }

    try {
        socketLog('open requested', {
            gameId: GAME_ID,
            attempt: gameSocketReconnectAttempts + 1,
        });
        gameSocket = new WebSocket(gameSocketUrl());
    } catch (error) {
        socketWarn('error creating socket', {
            gameId: GAME_ID,
            error: error,
        });
        enableGameSocketFallback();
        scheduleGameSocketReconnect();
        return;
    }

    gameSocket.addEventListener('open', function () {
        const wasReconnect = gameSocketEverConnected || gameSocketReconnectAttempts > 0 || gameSocketFallbackActive;

        gameSocketConnected = true;
        gameSocketEverConnected = true;
        gameSocketReconnectAttempts = 0;
        gameSocketFallbackActive = false;
        pauseGameStatePolling();
        pauseGameChatPolling();
        socketLog('open', {
            gameId: GAME_ID,
            reconnected: wasReconnect,
        });

        if (wasReconnect) {
            socketLog('reconnect complete; syncing latest state', { gameId: GAME_ID });
        }

        syncMovesFromServer({ source: wasReconnect ? 'websocket-reconnect' : 'websocket-open' });
        fetchGameChat();
    });

    gameSocket.addEventListener('message', function (event) {
        handleGameSocketMessage(event);
    });

    gameSocket.addEventListener('close', function (event) {
        socketLog('close', {
            gameId: GAME_ID,
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean,
        });
        gameSocketConnected = false;
        gameSocket = null;
        enableGameSocketFallback();

        if (shouldReconnectGameSocket(event)) {
            scheduleGameSocketReconnect();
        }
    });

    gameSocket.addEventListener('error', function (error) {
        socketWarn('error; enabling polling fallback', {
            gameId: GAME_ID,
            error: error,
        });
        enableGameSocketFallback();
    });
}

function enableGameSocketFallback() {
    if (gameSocketFallbackActive) {
        return;
    }

    gameSocketFallbackActive = true;
    startGameStatePolling();
    startGameChatPolling();
}

function scheduleGameSocketReconnect() {
    if (gameSocketReconnectId || !isMultiplayerMode()) {
        return;
    }

    gameSocketReconnectAttempts += 1;
    const delayMs = nextGameSocketReconnectDelay();

    socketLog('reconnect scheduled', {
        gameId: GAME_ID,
        attempt: gameSocketReconnectAttempts,
        delayMs: delayMs,
    });

    gameSocketReconnectId = setTimeout(function () {
        gameSocketReconnectId = null;
        socketLog('reconnect attempt', {
            gameId: GAME_ID,
            attempt: gameSocketReconnectAttempts,
        });
        connectGameSocket();
    }, delayMs);
}

function sendGameSocketMessage(message) {
    if (!gameSocketConnected || !gameSocket || gameSocket.readyState !== WebSocket.OPEN) {
        return false;
    }

    try {
        gameSocket.send(JSON.stringify(message));
        socketLog('sent', {
            gameId: GAME_ID,
            type: message.type,
        });
        return true;
    } catch (error) {
        socketWarn('send failed', {
            gameId: GAME_ID,
            type: message.type,
            error: error,
        });
        enableGameSocketFallback();
        scheduleGameSocketReconnect();
        return false;
    }
}

async function handleGameSocketMessage(event) {
    let data;

    try {
        data = JSON.parse(event.data);
    } catch (error) {
        socketWarn('received invalid message', {
            gameId: GAME_ID,
            data: event.data,
        });
        return;
    }

    socketLog('received', {
        gameId: GAME_ID,
        type: data.type,
        moveCount: data.state ? data.state.move_count : undefined,
        lastMoveId: data.state ? data.state.last_move_id : undefined,
        status: data.status,
    });

    if (data.type === 'connection.ready') {
        return;
    }

    if (data.type === 'move.created' && data.state) {
        pendingMoveSaveCount = Math.max(0, pendingMoveSaveCount - 1);
        await applyGameStateFromServer(data.state);
        return;
    }

    if (data.type === 'chat.message' && data.message) {
        appendGameChatMessage(data.message);
        return;
    }

    if (data.type === 'error') {
        pendingMoveSaveCount = Math.max(0, pendingMoveSaveCount - 1);
        socketWarn('server error', {
            gameId: GAME_ID,
            status: data.status,
            error: data.error,
        });
        syncMovesFromServer({ source: 'websocket-error' });
    }
}

function renderSavedMoveList() {
    moveList.replaceChildren();

    SAVED_MOVES.forEach((move, index) => {
        const moveItem = document.createElement('li');
        moveItem.innerText = `${move.move_number}. ${move.from} -> ${move.to}`;
        moveItem.style.cursor = 'pointer';

        moveItem.addEventListener('click', function () {
            clearQueuedMove();
            loadPositionUntil(index + 1);
        });

        moveList.appendChild(moveItem);
    });

    updatePgnBox();
}

function enableComputerEloSelect() {
    const eloSelect = document.getElementById('computer-elo');
    const playerColorSelect = document.getElementById('player-color');

    if (eloSelect) {
        eloSelect.disabled = analysisMode || SAVED_MOVES.length > 0;
    }

    if (playerColorSelect) {
        playerColorSelect.disabled = computerThinking || SAVED_MOVES.length > 0;
    }

    updateHistoryControls();
}

function undoComputerMove() {
    if (!isComputerMode() || computerThinking || SAVED_MOVES.length === 0) {
        return;
    }

    if (!confirm('Tem certeza de que deseja voltar sua última jogada?')) {
        return;
    }

    const movesToRemove = SAVED_MOVES.length % 2 === 0 ? 2 : 1;
    SAVED_MOVES.splice(Math.max(0, SAVED_MOVES.length - movesToRemove), movesToRemove);
    gameOver = false;
    hideGameStatus();
    setCoachComment(coachEnabled ? uiText('coach_enabled', 'Treinador habilitado. Vou comentar suas jogadas.') : '');
    loadPositionUntil(SAVED_MOVES.length);
    renderSavedMoveList();
    enableComputerEloSelect();
    saveComputerGameState();

    if (currentTurn === computerColor()) {
        askComputerMove();
    }
}

function resetComputerGame() {
    if (!isComputerMode() || computerThinking || SAVED_MOVES.length === 0) {
        return;
    }

    if (!confirm('Tem certeza de que deseja reiniciar a partida?')) {
        return;
    }

    SAVED_MOVES.splice(0, SAVED_MOVES.length);
    gameOver = false;
    finishedGameSynced = false;
    hideGameStatus();
    setCoachComment('');
    loadPositionUntil(0);
    renderSavedMoveList();
    enableComputerEloSelect();
    saveComputerGameState();

    if (currentTurn === computerColor()) {
        askComputerMove();
    }
}

function toggleCoach() {
    coachEnabled = !coachEnabled;
    updateHistoryControls();

    if (coachEnabled) {
        setCoachComment(uiText('coach_enabled', 'Treinador habilitado. Vou comentar suas jogadas.'));
    } else {
        setCoachComment('');
    }
    saveComputerGameState();
}

function setCoachComment(message) {
    const coachComment = document.getElementById('coach-comment');

    if (!coachComment) {
        return;
    }

    coachComment.innerText = message;
    coachComment.hidden = message === '';
}

function addTrainerChatMessage(message, type) {
    const log = document.getElementById('trainer-chat-log');

    if (!log) {
        return;
    }

    const item = document.createElement('div');
    item.classList.add('trainer-chat-message', `trainer-chat-message-${type}`);
    item.dataset.messageType = type;
    item.innerText = message;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
    saveComputerGameState();
}

function updateTrainerChatControls() {
    const submitButton = document.getElementById('trainer-chat-submit');
    const input = document.getElementById('trainer-chat-input');

    if (submitButton) {
        submitButton.disabled = trainerChatThinking;
        submitButton.innerText = trainerChatThinking ? uiText('thinking', 'Pensando...') : uiText('ask', 'Perguntar');
    }

    if (input) {
        input.disabled = trainerChatThinking;
    }
}

function trainerChatMoves() {
    if (typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE) {
        return SAVED_MOVES.slice(0, historyIndex);
    }

    return SAVED_MOVES;
}

function trainerChatLogState() {
    const log = document.getElementById('trainer-chat-log');

    if (!log) {
        return [];
    }

    return Array.from(log.children).map(item => ({
        type: item.dataset.messageType || (item.classList.contains('trainer-chat-message-user') ? 'user' : 'trainer'),
        message: item.innerText,
    }));
}

function restoreTrainerChatLog(messages) {
    const log = document.getElementById('trainer-chat-log');

    if (!log || !Array.isArray(messages)) {
        return;
    }

    log.replaceChildren();

    messages.forEach(entry => {
        const item = document.createElement('div');
        const type = entry.type === 'user' ? 'user' : 'trainer';
        item.classList.add('trainer-chat-message', `trainer-chat-message-${type}`);
        item.dataset.messageType = type;
        item.innerText = entry.message || '';
        log.appendChild(item);
    });

    log.scrollTop = log.scrollHeight;
}

function saveComputerGameState() {
    if (!isHomeComputerGame() || typeof window.sessionStorage === 'undefined') {
        return;
    }

    const eloSelect = document.getElementById('computer-elo');

    try {
        window.sessionStorage.setItem(COMPUTER_GAME_STATE_KEY, JSON.stringify({
            moves: SAVED_MOVES,
            playerColor: playerColor(),
            elo: eloSelect ? eloSelect.value : null,
            boardOrientation: boardOrientation,
            coachEnabled: coachEnabled,
            trainerMessages: trainerChatLogState(),
        }));
    } catch (error) {
        console.warn('No se pudo guardar la partida local:', error);
    }
}

function restoreComputerGameState() {
    if (!isHomeComputerGame() || typeof window.sessionStorage === 'undefined') {
        return;
    }

    let state;

    try {
        state = JSON.parse(window.sessionStorage.getItem(COMPUTER_GAME_STATE_KEY) || 'null');
    } catch (error) {
        return;
    }

    if (!state || !Array.isArray(state.moves)) {
        return;
    }

    SAVED_MOVES.splice(0, SAVED_MOVES.length, ...state.moves);

    if (state.playerColor && typeof PLAYER_COLOR !== 'undefined') {
        PLAYER_COLOR = state.playerColor;
        const playerColorSelect = document.getElementById('player-color');
        if (playerColorSelect) {
            playerColorSelect.value = PLAYER_COLOR;
        }
    }

    const eloSelect = document.getElementById('computer-elo');
    if (eloSelect && state.elo) {
        eloSelect.value = state.elo;
    }

    coachEnabled = Boolean(state.coachEnabled);
    boardOrientation = state.boardOrientation || playerColor();
    restoreTrainerChatLog(state.trainerMessages);
}

async function askTrainerChat(question) {
    trainerChatThinking = true;
    updateTrainerChatControls();
    addTrainerChatMessage(question, 'user');

    try {
        const response = await fetch('/trainer-chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                question: question,
                moves: trainerChatMoves(),
                player_color: playerColor(),
                language: typeof UI_LANGUAGE !== 'undefined' ? UI_LANGUAGE : 'pt',
            }),
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            console.error('Erro do chat do treinador:', data.error || response.statusText);
            addTrainerChatMessage(uiText('trainer_error', 'O treinador não conseguiu responder agora.'), 'trainer');
            return;
        }

        if (data.source) {
            console.log('Fonte do chat do treinador:', data.source);
        }

        addTrainerChatMessage(data.answer, 'trainer');
    } catch (error) {
        console.error('Erro ao perguntar ao treinador:', error);
        addTrainerChatMessage(uiText('trainer_error', 'O treinador não conseguiu responder agora.'), 'trainer');
    } finally {
        trainerChatThinking = false;
        updateTrainerChatControls();
    }
}

async function requestCoachAnalysis() {
    setCoachComment(uiText('trainer_analyzing', 'Treinador analisando...'));

    try {
        const response = await fetch('/coach-analysis/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                moves: SAVED_MOVES,
                player_color: playerColor(),
                language: typeof UI_LANGUAGE !== 'undefined' ? UI_LANGUAGE : 'pt',
            }),
        });

        const analysis = await response.json();

        if (!response.ok || analysis.error) {
            console.error('Erro do treinador:', analysis.error || response.statusText);
            setCoachComment(uiText('trainer_error', 'O treinador não conseguiu responder agora.'));
            return;
        }

        setCoachComment(analysis.comment || '');
    } catch (error) {
        console.error('Erro ao pedir análise do treinador:', error);
        setCoachComment(uiText('trainer_error', 'O treinador não conseguiu responder agora.'));
    }
}

document.getElementById('prev-move').addEventListener('click', function () {
    clearQueuedMove();
    if (historyIndex > 0) {
        loadPositionUntil(historyIndex - 1);
    }
});

document.getElementById('next-move').addEventListener('click', function () {
    clearQueuedMove();
    if (historyIndex < SAVED_MOVES.length) {
        loadPositionUntil(historyIndex + 1);
    }
});

document.getElementById('last-move').addEventListener('click', function () {
    clearQueuedMove();
    if (typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE) {
        loadPositionUntil(0);
    } else {
        loadPositionUntil(SAVED_MOVES.length);
    }
});

const undoComputerButton = document.getElementById('undo-computer-move');
if (undoComputerButton) {
    undoComputerButton.addEventListener('click', undoComputerMove);
}

const resetComputerButton = document.getElementById('reset-computer-game');
if (resetComputerButton) {
    resetComputerButton.addEventListener('click', resetComputerGame);
}

const toggleCoachButton = document.getElementById('toggle-coach');
if (toggleCoachButton) {
    toggleCoachButton.addEventListener('click', toggleCoach);
}

const computerEloSelect = document.getElementById('computer-elo');
if (computerEloSelect) {
    computerEloSelect.addEventListener('change', saveComputerGameState);
}

const flipBoardButton = document.getElementById('flip-board');
if (flipBoardButton) {
    flipBoardButton.addEventListener('click', function () {
        flipBoard();
        saveComputerGameState();
    });
}

if (offerDrawButton) {
    offerDrawButton.addEventListener('click', async function () {
        offerDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/offer-draw/`);
        } catch (error) {
            console.error('Erro ao oferecer empate:', error);
        } finally {
            offerDrawButton.disabled = gameOver;
        }
    });
}

if (acceptDrawButton) {
    acceptDrawButton.addEventListener('click', async function () {
        acceptDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/answer-draw/`, { accepted: true });
        } catch (error) {
            console.error('Erro ao aceitar empate:', error);
            acceptDrawButton.disabled = false;
        }
    });
}

if (rejectDrawButton) {
    rejectDrawButton.addEventListener('click', async function () {
        rejectDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/answer-draw/`, { accepted: false });
        } catch (error) {
            console.error('Erro ao recusar empate:', error);
        } finally {
            rejectDrawButton.disabled = false;
        }
    });
}

if (resignButton) {
    resignButton.addEventListener('click', function () {
        showResignConfirmPanel();
    });
}

if (cancelResignButton) {
    cancelResignButton.addEventListener('click', function () {
        hideResignConfirmPanel();
    });
}

if (confirmResignButton) {
    confirmResignButton.addEventListener('click', async function () {
        confirmResignButton.disabled = true;

        if (resignButton) {
            resignButton.disabled = true;
        }

        try {
            await postGameAction(`/games/${GAME_ID}/resign/`);
            hideResignConfirmPanel();
        } catch (error) {
            console.error('Erro ao desistir:', error);
            confirmResignButton.disabled = false;
            if (resignButton) {
                resignButton.disabled = false;
            }
        }
    });
}

if (gameChatToggle) {
    gameChatToggle.addEventListener('click', toggleGameChat);
}

if (gameChatClose) {
    gameChatClose.addEventListener('click', closeGameChat);
}

if (gameChatEmojiToggle && gameChatEmojiPanel) {
    gameChatEmojiToggle.addEventListener('click', function () {
        gameChatEmojiPanel.hidden = !gameChatEmojiPanel.hidden;
    });

    gameChatEmojiPanel.querySelectorAll('button').forEach(function (button) {
        button.addEventListener('click', function () {
            insertGameChatEmoji(button.innerText);
            gameChatEmojiPanel.hidden = true;
        });
    });
}

if (gameChatForm) {
    gameChatForm.addEventListener('submit', async function (event) {
        event.preventDefault();

        const text = gameChatInput ? gameChatInput.value.trim() : '';

        if (!text || !GAME_ID) {
            return;
        }

        gameChatInput.value = '';

        try {
            if (sendGameSocketMessage({ type: 'chat.send', text })) {
                return;
            }

            const response = await fetch(`/games/${GAME_ID}/chat/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                },
                body: JSON.stringify({ text }),
            });

            if (!response.ok) {
                return;
            }

            const data = await response.json();
            renderGameChat(data);
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
        }
    });
}

const analysisModeButton = document.getElementById('toggle-analysis-mode');
if (analysisModeButton) {
    analysisModeButton.addEventListener('click', toggleAnalysisMode);
}

const analysisPrevButton = document.getElementById('analysis-prev');
if (analysisPrevButton) {
    analysisPrevButton.addEventListener('click', showPreviousAnalysisPosition);
}

const analysisNextButton = document.getElementById('analysis-next');
if (analysisNextButton) {
    analysisNextButton.addEventListener('click', showNextAnalysisPosition);
}

const playerColorSelect = document.getElementById('player-color');
if (playerColorSelect) {
    playerColorSelect.value = playerColor();
    playerColorSelect.addEventListener('change', function () {
        if (!isComputerMode() || SAVED_MOVES.length > 0 || computerThinking) {
            playerColorSelect.value = playerColor();
            return;
        }

        PLAYER_COLOR = playerColorSelect.value;
        boardOrientation = playerColor();
        updateBoardOrientation();
        updateTurnIndicator();
        updateHistoryControls();
        saveComputerGameState();

        if (currentTurn === computerColor()) {
            askComputerMove();
        }
    });
}

const trainerChatForm = document.getElementById('trainer-chat-form');
function submitTrainerChatQuestion() {
    const input = document.getElementById('trainer-chat-input');
    const question = input ? input.value.trim() : '';

    if (!question || trainerChatThinking) {
        return;
    }

    input.value = '';
    askTrainerChat(question);
}

function savedMovesAsInternalPgn() {
    return SAVED_MOVES.map(move => {
        const promotion = move.promotion ? ` ${move.promotion}` : '';
        return `${move.move_number}. ${move.from} -> ${move.to}${promotion}`;
    }).join('\n');
}

function activateComputerTab(tabName) {
    document.querySelectorAll('[data-computer-tab]').forEach(button => {
        const isActive = button.dataset.computerTab === tabName;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    document.querySelectorAll('[data-computer-panel]').forEach(panel => {
        panel.hidden = panel.dataset.computerPanel !== tabName;
    });
}

document.querySelectorAll('[data-computer-tab]').forEach(button => {
    button.addEventListener('click', function () {
        activateComputerTab(button.dataset.computerTab);
    });
});

if (analyzeGameForm && analyzeGamePgn) {
    analyzeGameForm.addEventListener('submit', function () {
        analyzeGamePgn.value = savedMovesAsInternalPgn();
    });
}

if (trainerChatForm) {
    trainerChatForm.dataset.trainerChatBound = 'true';
    trainerChatForm.addEventListener('submit', function (event) {
        event.preventDefault();
        submitTrainerChatQuestion();
    });
}

const trainerChatInput = document.getElementById('trainer-chat-input');
if (trainerChatInput) {
    trainerChatInput.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
            return;
        }

        event.preventDefault();
        submitTrainerChatQuestion();
    });
}

document.addEventListener('gchess:before-language-change', saveComputerGameState);


function updatePgnBox() {
    const moves = Array.from(moveList.children)
        .map(item => item.innerText)
        .join('\n');

    pgnBox.innerText = moves;
}

function choosePromotionPiece(square, color) {
    promotionPending = true;

    document.querySelectorAll('.promotion-selector').forEach(selector => {
        selector.remove();
    });

    const selector = document.createElement('div');
    selector.classList.add('promotion-selector');

    if (getCol(square.dataset.coord) >= 4) {
        selector.classList.add('promotion-selector-left');
    }

    selector.addEventListener('click', function (event) {
        event.stopPropagation();
    });

    const options = [
        { type: 'queen', label: 'Dama' },
        { type: 'rook', label: 'Torre' },
        { type: 'bishop', label: 'Bispo' },
        { type: 'horse', label: 'Cavalo' },
    ];

    return new Promise(resolve => {
        options.forEach(option => {
            const button = document.createElement('button');
            button.type = 'button';
            button.classList.add('promotion-option');
            button.title = option.label;
            button.setAttribute('aria-label', option.label);
            button.appendChild(createPieceElement({
                type: option.type,
                color: color
            }));

            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                selector.remove();
                promotionPending = false;
                resolve(option.type);
            });

            selector.appendChild(button);
        });

        square.appendChild(selector);
    });
}

async function askComputerMove() {
    if (gameOver || currentTurn !== computerColor() || computerThinking) {
        return;
    }

    computerThinking = true;
    updateTurnIndicator();
    updateHistoryControls();

    const eloSelect = document.getElementById('computer-elo');
    const elo = eloSelect ? eloSelect.value : 1200;

    let move;

    try {
        const response = await fetch('/engine-move/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                moves: SAVED_MOVES,
                elo: elo,
            }),
        });

        move = await response.json();

        if (!response.ok || move.error) {
            console.error('Erro do computador:', move.error || response.statusText);
            computerThinking = false;
            updateTurnIndicator();
            updateHistoryControls();
            return;
        }
    } catch (error) {
        console.error('Erro ao pedir jogada do computador:', error);
        computerThinking = false;
        updateTurnIndicator();
        updateHistoryControls();
        return;
    }

    const fromSquare = getSquare(move.from);
    const toSquare = getSquare(move.to);

    if (!fromSquare || !toSquare) {
        computerThinking = false;
        updateTurnIndicator();
        updateHistoryControls();
        return;
    }

    await playMove(fromSquare, toSquare, true, move.promotion || null);
    computerThinking = false;
    updateTurnIndicator();
    updateHistoryControls();
}
