(function () {
    const statusElement = document.getElementById('game-detail-react-root');
    const boardElement = document.getElementById('board');
    const contextElement = document.getElementById('react-game-context-data');

    if (!boardElement || !contextElement) {
        return;
    }

    if (statusElement) {
        statusElement.dataset.reactStatus = 'booting';
    }

    if (!window.React || !window.ReactDOM) {
        if (statusElement) {
            statusElement.dataset.reactStatus = 'runtime-missing';
        }
        return;
    }

    const letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
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
    const pieceFallbacks = {
        queen_white: '?',
        queen_black: '?',
    };
    const pieceFileNames = {
        pawn_white: 'pawn_white.png',
    };

    function parseContext() {
        try {
            return JSON.parse(contextElement.textContent);
        } catch (error) {
            console.warn('No se pudo leer el contexto React de la partida:', error);
            return {};
        }
    }

    function Piece(props) {
        const piece = props.piece;
        const pieceKey = `${piece.type}_${piece.color}`;
        const fileName = pieceFileNames[pieceKey] || `${pieceKey}.png`;

        return React.createElement('img', {
            src: `/static/games/pieces/${fileName}`,
            alt: pieceKey,
            draggable: false,
            className: 'piece',
            onError: function (event) {
                const fallback = document.createElement('span');
                fallback.classList.add('piece-fallback');
                fallback.innerText = pieceFallbacks[pieceKey] || '?';
                event.currentTarget.replaceWith(fallback);
            },
        });
    }

    function ChessBoard() {
        const squares = [];

        for (let row = 8; row >= 1; row--) {
            for (let col = 0; col < 8; col++) {
                const coord = letters[col] + row;
                const isLight = (row + col) % 2 === 0;
                const position = initialPosition[coord];

                squares.push(React.createElement('div', {
                    key: coord,
                    className: `square ${isLight ? 'square-light' : 'square-dark'}`,
                    'data-coord': coord,
                    'data-color': position ? position.color : '',
                    'data-type': position ? position.type : '',
                    style: {
                        backgroundColor: isLight ? '#f0d9b5' : '#b58863',
                    },
                }, position ? React.createElement(Piece, { piece: position }) : null));
            }
        }

        return React.createElement(React.Fragment, null, squares);
    }

    function GameDetailApp(props) {
        const context = props.context;

        React.useEffect(function () {
            window.gchessReactGameDetailMounted = true;
            window.gchessReactGameDetailContext = context;
            boardElement.dataset.renderer = 'react';

            if (statusElement) {
                statusElement.dataset.reactStatus = 'mounted';
            }
        }, [context]);

        return React.createElement(ChessBoard);
    }

    const app = React.createElement(GameDetailApp, {
        context: parseContext(),
    });

    if (window.ReactDOM.render) {
        window.ReactDOM.render(app, boardElement);
    } else {
        window.ReactDOM.createRoot(boardElement).render(app);
    }
}());
