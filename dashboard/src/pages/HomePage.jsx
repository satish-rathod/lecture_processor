import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, FileText, Trash2, RefreshCw, Search } from 'lucide-react';

function HomePage() {
    const [recordings, setRecordings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [deleteModal, setDeleteModal] = useState(null);
    const [processing, setProcessing] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        fetchRecordings();
    }, []);

    const fetchRecordings = async () => {
        try {
            setLoading(true);
            const res = await fetch('/api/recordings');
            const data = await res.json();
            setRecordings(data.recordings || []);
        } catch (err) {
            console.error('Failed to fetch recordings', err);
        } finally {
            setLoading(false);
        }
    };

    const handleProcess = async (recording) => {
        if (processing) return;
        setProcessing(true);

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: recording.title,
                    videoPath: recording.videoPath,
                    skipSlideAnalysis: true
                })
            });
            const data = await res.json();
            navigate('/queue');
        } catch (err) {
            alert('Error starting process: ' + err.message);
        } finally {
            setProcessing(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteModal) return;

        try {
            const res = await fetch(`/api/recordings/${encodeURIComponent(deleteModal.id)}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                setDeleteModal(null);
                fetchRecordings();
            } else {
                const error = await res.json();
                alert('Delete failed: ' + error.detail);
            }
        } catch (err) {
            alert('Delete failed: ' + err.message);
        }
    };

    const filteredRecordings = recordings.filter(rec =>
        rec.title.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-semibold flex items-center gap-3">
                        <span className="text-3xl">📚</span>
                        Library
                    </h1>
                    <p className="text-muted-foreground text-sm mt-1">
                        {recordings.length} recording{recordings.length !== 1 ? 's' : ''}
                    </p>
                </div>

                <button
                    onClick={fetchRecordings}
                    className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                    <RefreshCw size={16} />
                    Refresh
                </button>
            </div>

            {/* Search */}
            <div className="relative mb-6">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                    type="text"
                    placeholder="Search recordings..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-muted border border-border rounded-md py-2.5 pl-10 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:border-primary"
                />
            </div>

            {/* Loading */}
            {loading && (
                <div className="text-center py-12 text-muted-foreground">
                    Loading library...
                </div>
            )}

            {/* Empty State */}
            {!loading && filteredRecordings.length === 0 && (
                <div className="text-center py-12">
                    <div className="text-4xl mb-4">📭</div>
                    <h3 className="font-medium mb-1">No recordings found</h3>
                    <p className="text-sm text-muted-foreground">
                        {searchQuery ? 'Try a different search term' : 'Download lectures using the browser extension'}
                    </p>
                </div>
            )}

            {/* Grid */}
            {!loading && filteredRecordings.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredRecordings.map((rec) => (
                        <div
                            key={rec.id}
                            className="bg-muted border border-border rounded-lg p-4 hover:border-border/50 transition-colors group"
                        >
                            {/* Header */}
                            <div className="flex justify-between items-start mb-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${rec.processed
                                        ? 'bg-success/20 text-success'
                                        : rec.status === 'processing'
                                            ? 'bg-warning/20 text-warning animate-pulse-slow'
                                            : 'bg-muted-foreground/20 text-muted-foreground'
                                    }`}>
                                    {rec.status}
                                </span>

                                <button
                                    onClick={(e) => { e.stopPropagation(); setDeleteModal(rec); }}
                                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive transition-all"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>

                            {/* Title */}
                            <h3 className="font-medium text-sm mb-2 line-clamp-2">
                                {rec.title}
                            </h3>

                            {/* Date */}
                            <p className="text-xs text-muted-foreground mb-4">
                                {rec.date || new Date(rec.downloadDate).toLocaleDateString()}
                            </p>

                            {/* Action Button */}
                            {rec.processed ? (
                                <button
                                    onClick={() => navigate(`/recording/${encodeURIComponent(rec.id)}`)}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                                >
                                    <FileText size={16} />
                                    View Notes
                                </button>
                            ) : (
                                <button
                                    onClick={() => handleProcess(rec)}
                                    disabled={processing || !rec.videoPath}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50"
                                >
                                    <Play size={16} />
                                    Process Video
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Delete Modal */}
            {deleteModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-[#252525] border border-border rounded-lg p-6 max-w-md w-full mx-4 animate-fade-in">
                        <h3 className="text-lg font-semibold mb-2">
                            Delete recording?
                        </h3>
                        <p className="text-sm text-muted-foreground mb-6">
                            This will permanently delete "<strong>{deleteModal.title}</strong>" and all processed notes.
                        </p>
                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={() => setDeleteModal(null)}
                                className="px-4 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleDelete}
                                className="px-4 py-2 rounded-md text-sm font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default HomePage;
