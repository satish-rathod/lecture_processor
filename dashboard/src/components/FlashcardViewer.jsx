
import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, RotateCw, Check, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

function FlashcardViewer({ url }) {
    const [cards, setCards] = useState([]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isFlipped, setIsFlipped] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (url) {
            fetchCards();
        }
    }, [url]);

    const fetchCards = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to load flashcards');

            const text = await res.text();
            parseCards(text);
        } catch (err) {
            console.error(err);
            setError('Failed to load flashcards');
        } finally {
            setLoading(false);
        }
    };

    const parseCards = (text) => {
        // Simple regex to parse **Q:** ... **A:** ... format
        // We look for segments that start with **Q:**
        const parsed = [];
        const lines = text.split('\n');

        let currentQ = null;
        let currentA = null;
        let mode = null; // 'Q' or 'A'

        for (const line of lines) {
            if (line.trim().startsWith('**Q:**')) {
                // If we have a pending pair, save it
                if (currentQ && currentA) {
                    parsed.push({ q: currentQ.trim(), a: currentA.trim() });
                }
                currentQ = line.replace('**Q:**', '').trim();
                currentA = '';
                mode = 'Q';
            } else if (line.trim().startsWith('**A:**')) {
                currentA = line.replace('**A:**', '').trim();
                mode = 'A';
            } else if (line.trim() === '---') {
                // Separator, save and reset
                if (currentQ && currentA) {
                    parsed.push({ q: currentQ.trim(), a: currentA.trim() });
                    currentQ = null;
                    currentA = null;
                    mode = null;
                }
            } else {
                if (mode === 'Q' && currentQ !== null) currentQ += '\n' + line;
                if (mode === 'A' && currentA !== null) currentA += '\n' + line;
            }
        }

        // Catch final card
        if (currentQ && currentA) {
            parsed.push({ q: currentQ.trim(), a: currentA.trim() });
        }

        setCards(parsed);
    };

    const handleNext = () => {
        if (currentIndex < cards.length - 1) {
            setIsFlipped(false);
            setCurrentIndex(prev => prev + 1);
        }
    };

    const handlePrev = () => {
        if (currentIndex > 0) {
            setIsFlipped(false);
            setCurrentIndex(prev => prev - 1);
        }
    };

    if (loading) return <div className="text-center p-12 text-muted-foreground">Loading flashcards...</div>;
    if (error) return <div className="text-center p-12 text-destructive">{error}</div>;
    if (cards.length === 0) return <div className="text-center p-12 text-muted-foreground">No flashcards found in this file.</div>;

    const currentCard = cards[currentIndex];

    return (
        <div className="max-w-2xl mx-auto py-8 px-4">
            <div className="mb-6 flex justify-between items-center text-sm text-muted-foreground">
                <span>Card {currentIndex + 1} of {cards.length}</span>
                <span>Click card to flip</span>
            </div>

            {/* Card Container */}
            <div
                className="perspective-1000 h-[400px] cursor-pointer group"
                onClick={() => setIsFlipped(!isFlipped)}
            >
                <div className={`relative w-full h-full transition-all duration-500 preserve-3d ${isFlipped ? 'rotate-y-180' : ''}`}>

                    {/* Front */}
                    <div className="absolute w-full h-full backface-hidden bg-card border border-border rounded-xl p-8 flex flex-col items-center justify-center text-center shadow-sm group-hover:shadow-md transition-shadow">
                        <div className="uppercase tracking-widest text-xs font-semibold text-primary mb-4">Question</div>
                        <div className="prose dark:prose-invert max-w-none text-xl font-medium">
                            <ReactMarkdown>{currentCard.q}</ReactMarkdown>
                        </div>
                        <div className="absolute bottom-6 text-muted-foreground text-sm flex items-center gap-2">
                            <RotateCw size={14} /> Flip
                        </div>
                    </div>

                    {/* Back */}
                    <div className="absolute w-full h-full backface-hidden bg-card border border-border rounded-xl p-8 flex flex-col items-center justify-center text-center shadow-sm rotate-y-180 bg-accent/5">
                        <div className="uppercase tracking-widest text-xs font-semibold text-success mb-4">Answer</div>
                        <div className="prose dark:prose-invert max-w-none text-lg">
                            <ReactMarkdown>{currentCard.a}</ReactMarkdown>
                        </div>
                    </div>

                </div>
            </div>

            {/* Controls */}
            <div className="flex items-center justify-between mt-8">
                <button
                    onClick={handlePrev}
                    disabled={currentIndex === 0}
                    className="p-2 rounded-full hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronLeft size={24} />
                </button>

                <div className="flex gap-4">
                    <button
                        onClick={() => setIsFlipped(!isFlipped)}
                        className="px-6 py-2 bg-primary text-primary-foreground rounded-full font-medium hover:opacity-90 transition-opacity flex items-center gap-2"
                    >
                        <RotateCw size={16} /> Flip
                    </button>
                </div>

                <button
                    onClick={handleNext}
                    disabled={currentIndex === cards.length - 1}
                    className="p-2 rounded-full hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronRight size={24} />
                </button>
            </div>

            <div className="mt-8 text-center">
                <p className="text-xs text-muted-foreground">
                    Use arrow keys or click buttons to navigate. Spacebar or click to flip.
                </p>
            </div>
        </div>
    );
}

export default FlashcardViewer;
