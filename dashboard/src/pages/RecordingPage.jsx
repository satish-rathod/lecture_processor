import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileText, BookOpen, MessageSquare, Image, FileDown, AlignLeft } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

function RecordingPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [recording, setRecording] = useState(null);
    const [activeTab, setActiveTab] = useState('notes');
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(true);
    const [contentLoading, setContentLoading] = useState(false);
    const [availableTabs, setAvailableTabs] = useState([]);

    useEffect(() => {
        fetchRecording();
    }, [id]);

    useEffect(() => {
        if (recording?.artifacts) {
            // Build tabs based on what's actually available
            const tabs = [];
            if (recording.artifacts.notes) tabs.push({ id: 'notes', label: 'Notes', icon: FileText });
            if (recording.artifacts.summary) tabs.push({ id: 'summary', label: 'Summary', icon: BookOpen });
            if (recording.artifacts.announcements) tabs.push({ id: 'announcements', label: 'Announcements', icon: MessageSquare });
            if (recording.artifacts.transcript) tabs.push({ id: 'transcript', label: 'Transcript', icon: AlignLeft });
            if (recording.artifacts.slides) tabs.push({ id: 'slides', label: 'Slides', icon: Image });

            setAvailableTabs(tabs);

            // Set default tab to first available if current not in list
            if (tabs.length > 0 && !tabs.find(t => t.id === activeTab)) {
                setActiveTab(tabs[0].id);
            }
        }
    }, [recording]);

    useEffect(() => {
        if (recording?.artifacts) {
            fetchContent(activeTab);
        }
    }, [activeTab, recording]);

    const fetchRecording = async () => {
        try {
            const res = await fetch('/api/recordings');
            const data = await res.json();
            const found = data.recordings?.find(r => r.id === decodeURIComponent(id));
            setRecording(found);
        } catch (err) {
            console.error('Failed to fetch recording', err);
        } finally {
            setLoading(false);
        }
    };

    const fetchContent = async (tab) => {
        if (!recording?.artifacts) return;

        setContentLoading(true);
        setContent('');

        const url = recording.artifacts[tab];

        if (!url) {
            setContent('*No content available for this tab.*');
            setContentLoading(false);
            return;
        }

        try {
            const res = await fetch(url);
            if (res.ok) {
                const text = await res.text();
                setContent(text || '*Empty file.*');
            } else {
                setContent('*Content not found.*');
            }
        } catch (err) {
            setContent('*Failed to load content.*');
        } finally {
            setContentLoading(false);
        }
    };

    const handleDownload = (artifactType) => {
        if (!recording?.artifacts?.[artifactType]) return;

        const url = recording.artifacts[artifactType];
        const link = document.createElement('a');
        link.href = url;
        link.download = `${recording.title.replace(/\s+/g, '_')}_${artifactType}.md`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    if (loading) {
        return (
            <div className="animate-fade-in flex items-center justify-center h-64">
                <p className="text-muted-foreground">Loading...</p>
            </div>
        );
    }

    if (!recording) {
        return (
            <div className="animate-fade-in">
                <button
                    onClick={() => navigate('/')}
                    className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-4"
                >
                    <ArrowLeft size={18} />
                    Back to Library
                </button>
                <p className="text-muted-foreground">Recording not found.</p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
                <div>
                    <button
                        onClick={() => navigate('/')}
                        className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-2 text-sm"
                    >
                        <ArrowLeft size={16} />
                        Back
                    </button>
                    <h1 className="text-2xl font-semibold">{recording.title}</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        {recording.date || 'Unknown date'} • {recording.status}
                    </p>
                </div>

                {/* Download Button */}
                {recording.artifacts?.notes && (
                    <button
                        onClick={() => handleDownload('notes')}
                        className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-muted hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <FileDown size={16} />
                        Download Notes
                    </button>
                )}
            </div>

            {/* Tabs - only show available ones */}
            {availableTabs.length > 0 ? (
                <>
                    <div className="flex gap-1 mb-6 border-b border-border pb-px overflow-x-auto">
                        {availableTabs.map((tab) => {
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap ${activeTab === tab.id
                                            ? 'border-primary text-foreground'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                        }`}
                                >
                                    <Icon size={16} />
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>

                    {/* Content */}
                    <div className="max-w-4xl">
                        {contentLoading ? (
                            <p className="text-muted-foreground">Loading content...</p>
                        ) : activeTab === 'slides' ? (
                            <div>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Slides are saved in the output folder at: <code className="bg-muted px-2 py-1 rounded">{recording.path}/slides/</code>
                                </p>
                            </div>
                        ) : (
                            <article className="markdown-content">
                                <ReactMarkdown>{content}</ReactMarkdown>
                            </article>
                        )}
                    </div>
                </>
            ) : (
                <div className="text-center py-12">
                    <p className="text-muted-foreground">No artifacts available yet. This recording may still be processing.</p>
                </div>
            )}
        </div>
    );
}

export default RecordingPage;
