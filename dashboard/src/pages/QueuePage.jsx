import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

function QueuePage() {
    const [queue, setQueue] = useState({ current: null, pending: [], completed: [] });
    const [processes, setProcesses] = useState({});
    const navigate = useNavigate();

    useEffect(() => {
        fetchQueue();
        const interval = setInterval(fetchQueue, 2000);
        return () => clearInterval(interval);
    }, []);

    const fetchQueue = async () => {
        try {
            // Fetch recordings to get processing status
            const res = await fetch('/api/recordings');
            const data = await res.json();

            const processing = data.recordings?.filter(r => r.status === 'processing') || [];
            const completed = data.recordings?.filter(r => r.processed) || [];
            const pending = data.recordings?.filter(r => r.status === 'downloaded') || [];

            setQueue({
                current: processing[0] || null,
                pending: pending.slice(0, 5),
                completed: completed.slice(0, 10)
            });
        } catch (err) {
            console.error('Failed to fetch queue', err);
        }
    };

    return (
        <div className="animate-fade-in max-w-4xl">
            {/* Header */}
            <div className="mb-8">
                <h1 className="text-2xl font-semibold flex items-center gap-3">
                    <span className="text-3xl">⚙️</span>
                    Processing Queue
                </h1>
                <p className="text-muted-foreground text-sm mt-1">
                    Monitor AI processing jobs
                </p>
            </div>

            {/* Currently Processing */}
            <section className="mb-8">
                <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
                    Currently Processing
                </h2>

                {queue.current ? (
                    <div className="bg-muted border border-border rounded-lg p-5">
                        <div className="flex items-start justify-between mb-4">
                            <div>
                                <h3 className="font-medium">{queue.current.title}</h3>
                                <p className="text-sm text-muted-foreground mt-1">
                                    Processing with AI...
                                </p>
                            </div>
                            <div className="flex items-center gap-2 text-warning">
                                <Loader2 size={18} className="animate-spin" />
                                <span className="text-sm font-medium">In Progress</span>
                            </div>
                        </div>

                        {/* Progress Bar */}
                        <div className="h-2 bg-background rounded-full overflow-hidden">
                            <div
                                className="h-full bg-primary rounded-full transition-all duration-500"
                                style={{ width: '45%' }}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            Generating lecture notes...
                        </p>
                    </div>
                ) : (
                    <div className="bg-muted/50 border border-border/50 border-dashed rounded-lg p-8 text-center">
                        <Clock size={24} className="mx-auto text-muted-foreground mb-2" />
                        <p className="text-sm text-muted-foreground">
                            No jobs currently processing
                        </p>
                    </div>
                )}
            </section>

            {/* Pending */}
            <section className="mb-8">
                <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
                    Ready to Process ({queue.pending.length})
                </h2>

                {queue.pending.length > 0 ? (
                    <div className="space-y-2">
                        {queue.pending.map((item, idx) => (
                            <div
                                key={item.id}
                                className="flex items-center justify-between bg-muted border border-border rounded-lg p-4"
                            >
                                <div className="flex items-center gap-3">
                                    <div className="w-6 h-6 rounded bg-muted-foreground/20 flex items-center justify-center text-xs font-medium text-muted-foreground">
                                        {idx + 1}
                                    </div>
                                    <span className="text-sm font-medium">{item.title}</span>
                                </div>
                                <span className="text-xs text-muted-foreground">
                                    Waiting
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        No recordings waiting to be processed.
                    </p>
                )}
            </section>

            {/* Recently Completed */}
            <section>
                <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
                    Recently Completed
                </h2>

                {queue.completed.length > 0 ? (
                    <div className="space-y-2">
                        {queue.completed.map((item) => (
                            <div
                                key={item.id}
                                onClick={() => navigate(`/recording/${encodeURIComponent(item.id)}`)}
                                className="flex items-center justify-between bg-muted border border-border rounded-lg p-4 cursor-pointer hover:border-primary/50 transition-colors"
                            >
                                <div className="flex items-center gap-3">
                                    <CheckCircle size={18} className="text-success" />
                                    <span className="text-sm font-medium">{item.title}</span>
                                </div>
                                <span className="text-xs text-primary">
                                    View →
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        No completed recordings yet.
                    </p>
                )}
            </section>
        </div>
    );
}

export default QueuePage;
