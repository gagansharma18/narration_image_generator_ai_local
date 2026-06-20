import React, { useState, useEffect, useRef } from 'react';
import { 
  Settings, 
  Download, 
  Play, 
  RefreshCw, 
  FileText, 
  Image as ImageIcon, 
  FolderDown, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  ChevronRight, 
  Edit3, 
  ZoomIn,
  Loader,
  Terminal,
  Trash2,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

const DEFAULT_TEXT_MODELS = [
  { id: 'Qwen/Qwen2.5-0.5B-Instruct', label: 'Qwen 2.5 0.5B Instruct [Disk: 0.9 GB | VRAM: ~1.5 GB]' },
  { id: 'meta-llama/Llama-3.2-1B-Instruct', label: 'Llama 3.2 1B Instruct [Disk: 2.2 GB | VRAM: ~2.5 GB] (Gated)' },
  { id: 'TinyLlama/TinyLlama-1.1B-Chat-v1.0', label: 'TinyLlama 1.1B Chat [Disk: 2.2 GB | VRAM: ~2.5 GB]' },
  { id: 'Qwen/Qwen2.5-1.5B-Instruct', label: 'Qwen 2.5 1.5B Instruct [Disk: 2.8 GB | VRAM: ~3.5 GB]' },
  { id: 'Qwen/Qwen2.5-3B-Instruct', label: 'Qwen 2.5 3B Instruct [Disk: 5.8 GB | VRAM: ~6.5 GB]' },
  { id: 'Qwen/Qwen3-4B-Instruct', label: 'Qwen 3 4B Instruct [Disk: 7.9 GB | VRAM: ~8.5 GB]' },
  { id: 'meta-llama/Llama-3.2-3B-Instruct', label: 'Llama 3.2 3B Instruct [Disk: 6.2 GB | VRAM: ~7.0 GB] (Gated)' }
];

const DEFAULT_IMAGE_MODELS = [
  { id: 'stabilityai/sd-turbo', label: 'SD Turbo (Fastest 1-step) [Disk: 2.0 GB | VRAM: ~3.0 GB]' },
  { id: 'runwayml/stable-diffusion-v1-5', label: 'Stable Diffusion v1.5 [Disk: 4.2 GB | VRAM: ~4.5 GB]' },
  { id: 'Lykon/dreamshaper-8', label: 'DreamShaper 8 (Stylized SD1.5) [Disk: 4.2 GB | VRAM: ~4.5 GB]' },
  { id: 'stabilityai/sdxl-turbo', label: 'SDXL Turbo (High Quality 1-step) [Disk: 6.9 GB | VRAM: ~7.5 GB]' }
];

export default function App() {
  // Configurations State
  const [config, setConfig] = useState({
    hf_token: '',
    selected_text_model: 'Qwen/Qwen2.5-0.5B-Instruct',
    selected_image_model: 'stabilityai/sd-turbo',
    num_inference_steps: 1,
    guidance_scale: 0.0,
    use_gpu: false,
    llm_provider: 'local',
    ollama_url: 'http://localhost:11434',
    ollama_model: 'qwen2.5:3b',
    openai_url: 'http://localhost:1234/v1',
    openai_model: 'qwen2.5-3b-instruct'
  });
  
  // Custom inputs for model IDs
  const [customTextModel, setCustomTextModel] = useState('');
  const [customImageModel, setCustomImageModel] = useState('');
  
  // App Workflow States
  const [activeStep, setActiveStep] = useState(1); // 1: Models, 2: Script, 3: Generation, 4: Storyboard
  const [scriptText, setScriptText] = useState('');
  const [segments, setSegments] = useState([]);
  const [isParsing, setIsParsing] = useState(false);
  
  // Model Download States
  const [modelsStatus, setModelsStatus] = useState({
    text_model: { status: 'not_started', progress: 0, downloaded: 0, total_size: 0, error: null },
    image_model: { status: 'not_started', progress: 0, downloaded: 0, total_size: 0, error: null }
  });
  
  // Generation Job State
  const [jobStatus, setJobStatus] = useState({
    status: 'idle',
    progress: 0,
    current_segment_index: 0,
    total_segments: 0,
    segments: [],
    error: null
  });
  
  // UI & Feedback states
  const [notification, setNotification] = useState(null);
  const [fullImageModal, setFullImageModal] = useState(null);
  const [isDownloadingZip, setIsDownloadingZip] = useState(false);
  
  // Remote models states
  const [remoteModels, setRemoteModels] = useState([]);
  const [isFetchingRemoteModels, setIsFetchingRemoteModels] = useState(false);
  const [remoteModelsError, setRemoteModelsError] = useState(null);
  
  // System Logs States
  const [logs, setLogs] = useState([]);
  const [logFilter, setLogFilter] = useState('all');
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);
  const terminalBodyRef = useRef(null);
  
  const prevStatusRef = useRef('idle');

  // Load config and logs on mount
  useEffect(() => {
    fetchConfig();
    fetchLogs();
  }, []);

  // Auto-scroll terminal to bottom when logs update
  useEffect(() => {
    if (terminalBodyRef.current) {
      terminalBodyRef.current.scrollTop = terminalBodyRef.current.scrollHeight;
    }
  }, [logs, isTerminalCollapsed]);

  // Connect to SSE stream for real-time status updates (no more polling!)
  useEffect(() => {
    const textModel = customTextModel || config.selected_text_model;
    const imageModel = customImageModel || config.selected_image_model;
    
    if (!textModel || !imageModel) return;
    
    const eventSource = new EventSource(`/api/stream?text_model=${encodeURIComponent(textModel)}&image_model=${encodeURIComponent(imageModel)}`);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.models) {
          setModelsStatus(data.models);
        }
        
        if (data.job) {
          setJobStatus(data.job);
          if (data.job.segments && data.job.segments.length > 0) {
            setSegments(data.job.segments);
          }
          
          // Handle transition notifications
          const prevStatus = prevStatusRef.current;
          const nextStatus = data.job.status;
          
          if (nextStatus === 'running') {
            // Automatically switch step to 3 on mount/update if generation is currently running
            setActiveStep(prev => prev === 1 || prev === 2 ? 3 : prev);
          }
          
          if (prevStatus === 'running' && nextStatus === 'completed') {
            setActiveStep(4);
            showNotification('Storyboard images generated successfully!', 'success');
          } else if (prevStatus === 'running' && nextStatus === 'failed') {
            showNotification(`Generation failed: ${data.job.error || 'Unknown error'}`, 'danger');
          }
          
          prevStatusRef.current = nextStatus;
        }

        if (data.logs) {
          setLogs(data.logs);
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };
    
    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
    };
    
    return () => {
      eventSource.close();
    };
  }, [config.selected_text_model, config.selected_image_model, customTextModel, customImageModel]);

  const showNotification = (message, type = 'info') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 5000);
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        if (data.selected_text_model) {
          const isDefaultText = DEFAULT_TEXT_MODELS.some(m => m.id === data.selected_text_model);
          setCustomTextModel(isDefaultText ? '' : data.selected_text_model);
        }
        if (data.selected_image_model) {
          const isDefaultImage = DEFAULT_IMAGE_MODELS.some(m => m.id === data.selected_image_model);
          setCustomImageModel(isDefaultImage ? '' : data.selected_image_model);
        }
      }
    } catch (err) {
      showNotification('Failed to load config file.', 'danger');
    }
  };

  const fetchRemoteModels = async (provider, url) => {
    if (!url) return;
    setIsFetchingRemoteModels(true);
    setRemoteModelsError(null);
    try {
      const endpoint = provider === 'ollama' 
        ? `/api/ollama/models?url=${encodeURIComponent(url)}` 
        : `/api/openai/models?url=${encodeURIComponent(url)}`;
      const res = await fetch(endpoint);
      if (res.ok) {
        const data = await res.json();
        setRemoteModels(data.models || []);
      } else {
        const err = await res.json();
        setRemoteModelsError(err.detail || 'Could not reach server');
        setRemoteModels([]);
      }
    } catch (e) {
      setRemoteModelsError('Could not reach local server');
      setRemoteModels([]);
    } finally {
      setIsFetchingRemoteModels(false);
    }
  };

  useEffect(() => {
    if (config.llm_provider === 'ollama') {
      fetchRemoteModels('ollama', config.ollama_url);
    } else if (config.llm_provider === 'openai_compatible') {
      fetchRemoteModels('openai_compatible', config.openai_url);
    } else {
      setRemoteModels([]);
      setRemoteModelsError(null);
    }
  }, [config.llm_provider, config.ollama_url, config.openai_url]);

  // Auto-select remote model when remoteModels list is loaded
  useEffect(() => {
    if (remoteModels.length > 0) {
      if (config.llm_provider === 'ollama') {
        if (!remoteModels.includes(config.ollama_model)) {
          const firstModel = remoteModels[0];
          setConfig(prev => ({ ...prev, ollama_model: firstModel }));
          handleSaveConfig({ ...config, ollama_model: firstModel });
        }
      } else if (config.llm_provider === 'openai_compatible') {
        if (!remoteModels.includes(config.openai_model)) {
          const firstModel = remoteModels[0];
          setConfig(prev => ({ ...prev, openai_model: firstModel }));
          handleSaveConfig({ ...config, openai_model: firstModel });
        }
      }
    }
  }, [remoteModels, config.llm_provider]);

  const fetchLogs = async () => {
    try {
      const res = await fetch('/api/logs');
      if (res.ok) {
        const data = await res.json();
        setLogs(data);
      }
    } catch (err) {
      console.error('Error fetching logs:', err);
    }
  };

  const handleClearLogs = async () => {
    try {
      const res = await fetch('/api/logs/clear', { method: 'POST' });
      if (res.ok) {
        setLogs([{
          timestamp: new Date().toLocaleTimeString(),
          category: 'system',
          level: 'INFO',
          message: 'Log window cleared.'
        }]);
        showNotification('Logs cleared.', 'success');
      }
    } catch (err) {
      console.error('Error clearing logs:', err);
    }
  };

  const handleSaveConfig = async (updatedConfig = config) => {
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedConfig)
      });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        if (data.selected_text_model) {
          const isDefaultText = DEFAULT_TEXT_MODELS.some(m => m.id === data.selected_text_model);
          setCustomTextModel(isDefaultText ? '' : data.selected_text_model);
        }
        if (data.selected_image_model) {
          const isDefaultImage = DEFAULT_IMAGE_MODELS.some(m => m.id === data.selected_image_model);
          setCustomImageModel(isDefaultImage ? '' : data.selected_image_model);
        }
        showNotification('Config saved successfully.', 'success');
      }
    } catch (err) {
      showNotification('Failed to save configuration.', 'danger');
    }
  };

  const triggerModelDownload = async (repoId) => {
    if (!repoId) return;
    try {
      const res = await fetch(`/api/models/download?repo_id=${encodeURIComponent(repoId)}`, {
        method: 'POST'
      });
      if (res.ok) {
        showNotification(`Downloading ${repoId} in background...`, 'info');
      } else {
        const errData = await res.json();
        showNotification(`Download trigger failed: ${errData.detail}`, 'danger');
      }
    } catch (err) {
      showNotification('Failed to trigger download.', 'danger');
    }
  };

  const handleLoadSampleScript = async () => {
    try {
      const res = await fetch('/api/script/sample');
      if (res.ok) {
        const data = await res.json();
        if (data.content) {
          setScriptText(data.content);
          showNotification('Loaded sample script.', 'success');
        } else {
          showNotification('sample_script.md is empty.', 'warning');
        }
      }
    } catch (err) {
      showNotification('Failed to load sample script.', 'danger');
    }
  };

  const handleParseScript = async () => {
    if (!scriptText.trim()) {
      showNotification('Please enter or load a script first.', 'warning');
      return;
    }
    setIsParsing(true);
    try {
      const textModel = customTextModel || config.selected_text_model;
      const res = await fetch('/api/script/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          script_text: scriptText,
          custom_text_model: textModel
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        setSegments(data.segments);
        setActiveStep(3);
        showNotification('Script parsed and prompts generated by local LLM!', 'success');
      } else {
        const err = await res.json();
        showNotification(`Failed to parse script: ${err.detail}`, 'danger');
      }
    } catch (err) {
      showNotification('Failed to communicate with LLM parser.', 'danger');
    } finally {
      setIsParsing(false);
    }
  };

  const handleUpdateSegmentPrompt = (id, newPrompt) => {
    setSegments(prev => prev.map(s => s.id === id ? { ...s, visual_prompt: newPrompt } : s));
  };

  const handleStartGeneration = async () => {
    if (segments.length === 0) {
      showNotification('No script segments to generate.', 'warning');
      return;
    }
    
    // Check if models are downloaded
    const imgModel = customImageModel || config.selected_image_model;
    const imgModelStatus = modelsStatus.image_model.status;
    if (imgModelStatus !== 'completed') {
      showNotification('Please ensure the selected Image Generation Model is fully downloaded first!', 'warning');
      setActiveStep(1);
      return;
    }
    
    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          segments: segments,
          custom_image_model: imgModel
        })
      });
      
      if (res.ok) {
        setJobStatus(prev => ({ ...prev, status: 'running', progress: 0 }));
        showNotification('Started image generation pipeline...', 'info');
      } else {
        const err = await res.json();
        showNotification(`Failed to start generation: ${err.detail}`, 'danger');
      }
    } catch (err) {
      showNotification('Error running generation command.', 'danger');
    }
  };

  const handleDownloadZip = async () => {
    setIsDownloadingZip(true);
    try {
      const response = await fetch('/api/images/download-all', {
        method: 'POST'
      });
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = "storyboard_images.zip";
        document.body.appendChild(a);
        a.click();
        a.remove();
        showNotification('ZIP downloaded successfully.', 'success');
      } else {
        const err = await response.json();
        showNotification(`Failed to download ZIP: ${err.detail}`, 'danger');
      }
    } catch (err) {
      showNotification('Error downloading ZIP storyboard.', 'danger');
    } finally {
      setIsDownloadingZip(false);
    }
  };

  const handleResetJob = async () => {
    try {
      const res = await fetch('/api/jobs/reset', { method: 'POST' });
      if (res.ok) {
        setJobStatus({
          status: 'idle',
          progress: 0,
          current_segment_index: 0,
          total_segments: 0,
          segments: [],
          error: null
        });
        setSegments([]);
        setActiveStep(2);
        showNotification('Workspace reset successfully.', 'success');
      }
    } catch (err) {
      showNotification('Failed to reset workspace.', 'danger');
    }
  };

  const formatSize = (bytes) => {
    if (!bytes) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return <span className="badge badge-success"><CheckCircle size={12} style={{marginRight: 4}} /> Cached / Ready</span>;
      case 'downloading':
        return <span className="badge badge-warning"><Loader size={12} className="spinner" style={{marginRight: 4}} /> Downloading</span>;
      case 'fetching_info':
        return <span className="badge badge-info"><Loader size={12} className="spinner" style={{marginRight: 4}} /> Fetching HF Info</span>;
      case 'queued':
        return <span className="badge badge-info">Queued</span>;
      case 'interrupted':
        return <span className="badge" style={{background: 'rgba(245, 158, 11, 0.2)', color: '#F59E0B', display: 'inline-flex', alignItems: 'center'}}><AlertCircle size={12} style={{marginRight: 4}} /> Interrupted</span>;
      case 'failed':
        return <span className="badge badge-danger"><XCircle size={12} style={{marginRight: 4}} /> Error</span>;
      default:
        return <span className="badge badge-muted">Not Started</span>;
    }
  };

  const renderRemoteModelSelector = (provider, url, selectedModel, onSelect) => {
    const isModelInList = remoteModels.includes(selectedModel);
    const dropdownVal = isModelInList ? selectedModel : '';
    
    return (
      <div className="form-group" style={{ margin: 0 }}>
        <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Model Name</span>
          {isFetchingRemoteModels && <span style={{ fontSize: '0.75rem', color: 'var(--accent)' }}>Fetching...</span>}
        </label>
        
        {isFetchingRemoteModels ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            <Loader size={14} className="spinner text-accent" />
            <span>Scanning server for models...</span>
          </div>
        ) : remoteModels.length > 0 ? (
          <select
            className="text-input"
            value={dropdownVal}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled>-- Select a Model --</option>
            {remoteModels.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        ) : (
          <div style={{ padding: '0.75rem', background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.25rem' }}>
            <div style={{ display: 'flex', gap: '0.35rem', color: 'var(--danger)', fontSize: '0.8rem', alignItems: 'center' }}>
              <AlertCircle size={14} style={{ flexShrink: 0 }} />
              <span style={{ fontWeight: 500 }}>Connection Failed: Server Offline</span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, lineHeight: '1.3' }}>
              Could not connect to {provider === 'ollama' ? 'Ollama' : 'LM Studio'} at <code>{url}</code>. Please check if your server is running.
            </p>
            <button 
              type="button" 
              className="btn btn-secondary" 
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', alignSelf: 'flex-start', marginTop: '0.25rem' }} 
              onClick={() => fetchRemoteModels(provider, url)}
            >
              Retry Connection
            </button>
          </div>
        )}
      </div>
    );
  };

  const renderModelDownloader = (type, displayName, defaultModels, selectedVal, setSelectedVal, customVal, setCustomVal, statusObj) => {
    const isCustom = selectedVal === 'custom' || (selectedVal && !defaultModels.some(m => m.id === selectedVal));
    const activeRepo = isCustom ? customVal : selectedVal;
    
    return (
      <div className="glass-panel" style={{ marginBottom: '1.25rem' }}>
        <h3 style={{ fontSize: '1.05rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Download size={16} className="text-accent" />
          {displayName}
        </h3>
        
        <div className="form-group">
          <label className="form-label">Select Model</label>
          <select 
            className="text-input"
            value={isCustom ? 'custom' : selectedVal}
            onChange={(e) => {
              const val = e.target.value;
              if (val === 'custom') {
                setSelectedVal('custom');
              } else {
                setSelectedVal(val);
                setCustomVal('');
                handleSaveConfig({ 
                  ...config, 
                  [type === 'text' ? 'selected_text_model' : 'selected_image_model']: val,
                  // Auto-adjust steps for fast models
                  num_inference_steps: val.includes('turbo') || val.includes('schnell') ? 1 : 20,
                  guidance_scale: val.includes('turbo') || val.includes('schnell') ? 0.0 : 7.5
                });
              }
            }}
          >
            {defaultModels.map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
            <option value="custom">Custom Model (Enter Repo ID)</option>
          </select>
        </div>

        {isCustom && (
          <div className="form-group">
            <label className="form-label">Hugging Face Repository ID</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input 
                type="text" 
                className="text-input" 
                placeholder="e.g. org/model-name"
                value={customVal}
                onChange={(e) => setCustomVal(e.target.value)}
              />
              <button 
                className="btn btn-secondary"
                onClick={() => handleSaveConfig({
                  ...config,
                  [type === 'text' ? 'selected_text_model' : 'selected_image_model']: customVal
                })}
              >
                Set
              </button>
            </div>
          </div>
        )}

        <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Status:</span>
          {getStatusBadge(statusObj.status)}
        </div>

        {(statusObj.status === 'downloading' || statusObj.status === 'interrupted' || statusObj.status === 'fetching_info' || statusObj.status === 'queued') && (
          <div style={{ marginTop: '0.75rem' }}>
            {(statusObj.status === 'downloading' || statusObj.status === 'interrupted') && (
              <>
                <div className="progress-container">
                  <div className="progress-bar" style={{ width: `${statusObj.progress}%` }}></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginTop: '0.35rem', color: 'var(--text-secondary)' }}>
                  <span>{formatSize(statusObj.downloaded)} of {formatSize(statusObj.total_size)}</span>
                  <span>{Math.round(statusObj.progress)}%</span>
                </div>
              </>
            )}
            
            {(statusObj.status === 'downloading' || statusObj.status === 'fetching_info' || statusObj.status === 'queued') && (
              <button
                className="btn btn-secondary"
                style={{
                  width: '100%',
                  marginTop: '0.75rem',
                  fontSize: '0.8rem',
                  padding: '0.35rem',
                  color: '#EF4444',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  background: 'rgba(239, 68, 68, 0.05)'
                }}
                onClick={async () => {
                  try {
                    const res = await fetch(`/api/models/cancel?repo_id=${encodeURIComponent(activeRepo)}`, { method: 'POST' });
                    if (res.ok) {
                      showNotification(`Cancelled downloading ${activeRepo}`, 'warning');
                    }
                  } catch (err) {
                    showNotification('Failed to cancel download.', 'danger');
                  }
                }}
              >
                Cancel Download
              </button>
            )}
          </div>
        )}

        {statusObj.error && (
          <div style={{ marginTop: '0.75rem' }}>
            <div style={{ display: 'flex', gap: '0.35rem', color: 'var(--danger)', fontSize: '0.8rem', alignItems: 'flex-start' }}>
              <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
              <span>{statusObj.error}</span>
            </div>
            {statusObj.error.toLowerCase().includes('gated') && (
              <div style={{
                marginTop: '0.5rem',
                padding: '0.5rem',
                background: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.2)',
                borderRadius: '4px',
                fontSize: '0.75rem',
                color: '#F59E0B'
              }}>
                <strong>Gated Model Access Required:</strong> Make sure you have accepted the license terms on Hugging Face at 
                <a href={`https://huggingface.co/${activeRepo}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', marginLeft: '4px', textDecoration: 'underline' }}>
                  {activeRepo}
                </a>, and pasted your HF Token in the Configuration panel above.
              </div>
            )}
          </div>
        )}

        {statusObj.status !== 'completed' && statusObj.status !== 'downloading' && statusObj.status !== 'fetching_info' && (
          <button 
            className="btn btn-primary" 
            style={{ 
              width: '100%', 
              marginTop: '1rem', 
              fontSize: '0.85rem', 
              padding: '0.5rem',
              background: statusObj.status === 'interrupted' ? 'linear-gradient(135deg, #F59E0B, #D97706)' : undefined,
              borderColor: statusObj.status === 'interrupted' ? '#D97706' : undefined
            }}
            onClick={() => triggerModelDownload(activeRepo)}
          >
            {statusObj.status === 'interrupted' 
              ? `Resume Download (${Math.round(statusObj.progress)}% completed)` 
              : 'Download / Verify Model Cache'}
          </button>
        )}
      </div>
    );
  };

  const renderTerminalWindow = () => {
    // Filter logs based on category
    const filteredLogs = logs.filter(log => {
      if (logFilter === 'all') return true;
      return log.category === logFilter;
    });

    return (
      <div className="terminal-window">
        <div className="terminal-header">
          <div className="terminal-title">
            <span className="terminal-indicator"></span>
            <Terminal size={14} />
            <span>SYSTEM MONITORING CONSOLE</span>
          </div>
          <div className="terminal-actions">
            <button 
              className="icon-btn" 
              onClick={handleClearLogs} 
              title="Clear Console"
              style={{ padding: '0.2rem', color: 'var(--text-muted)' }}
            >
              <Trash2 size={14} />
            </button>
            <button 
              className="icon-btn" 
              onClick={() => setIsTerminalCollapsed(!isTerminalCollapsed)} 
              title={isTerminalCollapsed ? "Expand Console" : "Collapse Console"}
              style={{ padding: '0.2rem', color: 'var(--text-muted)' }}
            >
              {isTerminalCollapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>

        {!isTerminalCollapsed && (
          <>
            <div className="terminal-filter-bar">
              <button 
                className={`terminal-filter-btn ${logFilter === 'all' ? 'active' : ''}`}
                onClick={() => setLogFilter('all')}
              >
                ALL LOGS ({logs.length})
              </button>
              <button 
                className={`terminal-filter-btn ${logFilter === 'downloader' ? 'active' : ''}`}
                onClick={() => setLogFilter('downloader')}
              >
                DOWNLOADS ({logs.filter(l => l.category === 'downloader').length})
              </button>
              <button 
                className={`terminal-filter-btn ${logFilter === 'llm' ? 'active' : ''}`}
                onClick={() => setLogFilter('llm')}
              >
                SCRIPT ({logs.filter(l => l.category === 'llm').length})
              </button>
              <button 
                className={`terminal-filter-btn ${logFilter === 'image' ? 'active' : ''}`}
                onClick={() => setLogFilter('image')}
              >
                IMAGES ({logs.filter(l => l.category === 'image').length})
              </button>
              <button 
                className={`terminal-filter-btn ${logFilter === 'system' ? 'active' : ''}`}
                onClick={() => setLogFilter('system')}
              >
                SYSTEM ({logs.filter(l => l.category === 'system').length})
              </button>
            </div>
            
            <div className="terminal-body" ref={terminalBodyRef}>
              {filteredLogs.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic', padding: '0.5rem 0' }}>
                  No logs available for this filter.
                </div>
              ) : (
                filteredLogs.map((log, index) => (
                  <div key={index} className={`terminal-log-row log-level-${log.level.toLowerCase()}`}>
                    <span className="log-timestamp">[{log.timestamp}]</span>
                    <span className={`log-category log-category-${log.category}`}>
                      {log.category}
                    </span>
                    <span className="log-message">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="app-container">
      {/* Toast Notification */}
      {notification && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          background: notification.type === 'success' ? 'var(--success)' : notification.type === 'danger' ? 'var(--danger)' : 'var(--primary)',
          color: '#FFF',
          padding: '0.75rem 1.5rem',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 2000,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          fontFamily: 'var(--font-family)',
          fontSize: '0.9rem',
          fontWeight: 600
        }}>
          {notification.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {notification.message}
        </div>
      )}

      {/* Header */}
      <header className="header">
        <div className="logo-section">
          <div style={{
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 15px var(--primary-glow)'
          }}>
            <ImageIcon size={20} color="#FFF" />
          </div>
          <div>
            <h1>Paint storyboard AI</h1>
            <div className="tagline">Local YouTube Script to MS Paint Image Generator</div>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {jobStatus.status === 'running' && (
            <div className="glass-panel" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Loader size={14} className="spinner text-accent" />
                Generating scene {jobStatus.current_segment_index + 1} of {jobStatus.total_segments}
              </span>
              <div className="progress-container" style={{ width: '80px', height: '6px', margin: 0 }}>
                <div className="progress-bar" style={{ width: `${jobStatus.progress}%` }}></div>
              </div>
            </div>
          )}
          {segments.length > 0 && (
            <button className="btn btn-secondary" onClick={handleResetJob}>
              Reset Workspace
            </button>
          )}
        </div>
      </header>

      {/* Stepper progress */}
      <div className="stepper">
        <div className={`step ${activeStep >= 1 ? 'active' : ''} ${activeStep > 1 ? 'completed' : ''}`} onClick={() => setActiveStep(1)} style={{cursor: 'pointer'}}>
          <span className="step-num">{activeStep > 1 ? <CheckCircle size={14} /> : '1'}</span>
          Download Models
        </div>
        <ChevronRight size={16} className="text-muted" style={{alignSelf: 'center'}} />
        <div className={`step ${activeStep >= 2 ? 'active' : ''} ${activeStep > 2 ? 'completed' : ''}`} onClick={() => segments.length > 0 ? setActiveStep(2) : null} style={{cursor: segments.length > 0 ? 'pointer' : 'not-allowed'}}>
          <span className="step-num">{activeStep > 2 ? <CheckCircle size={14} /> : '2'}</span>
          Input Script
        </div>
        <ChevronRight size={16} className="text-muted" style={{alignSelf: 'center'}} />
        <div className={`step ${activeStep >= 3 ? 'active' : ''} ${activeStep > 3 ? 'completed' : ''}`} onClick={() => segments.length > 0 ? setActiveStep(3) : null} style={{cursor: segments.length > 0 ? 'pointer' : 'not-allowed'}}>
          <span className="step-num">{activeStep > 3 ? <CheckCircle size={14} /> : '3'}</span>
          Storyboard Prompt Editor
        </div>
        <ChevronRight size={16} className="text-muted" style={{alignSelf: 'center'}} />
        <div className={`step ${activeStep >= 4 ? 'active' : ''}`} onClick={() => segments.some(s => s.image_url) ? setActiveStep(4) : null} style={{cursor: segments.some(s => s.image_url) ? 'pointer' : 'not-allowed'}}>
          <span className="step-num">4</span>
          Storyboard Output
        </div>
      </div>

      {/* Dashboard Main Grid */}
      <div className="dashboard-grid">
        
        {/* LEFT SIDEBAR: CONFIG & MODELS */}
        <aside className="sidebar">
          {/* Config Panel */}
          <div className="glass-panel">
            <h2 style={{ fontSize: '1.25rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Settings size={18} className="text-primary" />
              Inference settings
            </h2>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">Inference Steps</label>
                <input 
                  type="number" 
                  className="text-input"
                  value={config.num_inference_steps}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 1;
                    setConfig(prev => ({ ...prev, num_inference_steps: val }));
                  }}
                  onBlur={() => handleSaveConfig()}
                  min="1"
                  max="100"
                />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">Guidance Scale</label>
                <input 
                  type="number" 
                  step="0.1"
                  className="text-input"
                  value={config.guidance_scale}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value) || 0.0;
                    setConfig(prev => ({ ...prev, guidance_scale: val }));
                  }}
                  onBlur={() => handleSaveConfig()}
                  min="0"
                  max="20"
                />
              </div>
            </div>
          </div>

          {/* Active Engine Status Panel (Read-only summary) */}
          <div className="glass-panel" style={{ marginTop: '1rem' }}>
            <h3 style={{ fontSize: '1.05rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
              <FileText size={16} className="text-accent" />
              Active Configuration
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.85rem' }}>
              <div>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '0.15rem' }}>LLM Service Provider:</span>
                <span className="badge badge-info" style={{ fontWeight: 600 }}>
                  {config.llm_provider === 'local' ? 'Local Model (Hugging Face)' : config.llm_provider === 'ollama' ? 'Ollama API' : 'LM Studio / OpenAI API'}
                </span>
              </div>
              
              <div>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '0.15rem' }}>Active Text Model:</span>
                <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                  {config.llm_provider === 'local' 
                    ? (config.selected_text_model || 'None')
                    : config.llm_provider === 'ollama' 
                      ? (config.ollama_model || 'None')
                      : (config.openai_model || 'None')}
                </span>
              </div>

              <div style={{ borderTop: '1px dashed var(--border)', paddingTop: '0.75rem' }}>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '0.15rem' }}>Active Image Model:</span>
                <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)', display: 'block', marginBottom: '0.25rem', wordBreak: 'break-all' }}>
                  {config.selected_image_model || 'None'}
                </span>
                <span style={{ fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center' }}>
                  Status: &nbsp;{getStatusBadge(modelsStatus.image_model.status)}
                </span>
              </div>
            </div>
          </div>
        </aside>

        {/* RIGHT COLUMN: WORKSPACE STEPS */}
        <main className="glass-panel highlight-border" style={{ minHeight: '600px' }}>
                   {/* STEP 1: CONFIGURE & VERIFY MODELS */}
          {activeStep === 1 && (() => {
            const isImageModelReady = modelsStatus.image_model.status === 'completed';
            const isTextModelReady = config.llm_provider === 'local' 
              ? modelsStatus.text_model.status === 'completed'
              : config.llm_provider === 'ollama'
                ? (config.ollama_model && remoteModels.includes(config.ollama_model))
                : (config.openai_model && remoteModels.includes(config.openai_model));
            const canProceed = isImageModelReady && isTextModelReady;

            return (
              <div>
                <h2 style={{ fontSize: '1.4rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Settings size={20} className="text-primary" />
                  Model Configuration & Setup
                </h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
                  Set up the Text LLM for parsing scripts and the local Image model for storyboard rendering.
                </p>

                <div className="setup-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                  {/* Text Generation Panel */}
                  <div className="glass-panel" style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', padding: '1.25rem' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
                      <FileText size={18} className="text-accent" />
                      1. Text Generation LLM
                    </h3>

                    <div className="form-group" style={{ marginBottom: '1rem' }}>
                      <label className="form-label">LLM Service Provider</label>
                      <select 
                        className="text-input" 
                        value={config.llm_provider || 'local'}
                        onChange={(e) => {
                          const val = e.target.value;
                          setConfig(prev => ({ ...prev, llm_provider: val }));
                          handleSaveConfig({ ...config, llm_provider: val });
                        }}
                      >
                        <option value="local">Local Model (Hugging Face Download)</option>
                        <option value="ollama">Ollama (Local Server API)</option>
                        <option value="openai_compatible">LM Studio / OpenAI Compatible API</option>
                      </select>
                    </div>

                    {config.llm_provider === 'local' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>Hugging Face Token</span>
                            <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', fontSize: '0.75rem', textDecoration: 'none' }}>
                              Get Token ↗
                            </a>
                          </label>
                          <input 
                            type="password" 
                            className="text-input" 
                            placeholder="Paste hf_token if needed..." 
                            value={config.hf_token}
                            onChange={(e) => setConfig(prev => ({ ...prev, hf_token: e.target.value }))}
                            onBlur={() => handleSaveConfig()}
                          />
                        </div>
                        
                        <div style={{ borderTop: '1px dashed var(--border)', paddingTop: '1rem' }}>
                          {renderModelDownloader(
                            'text',
                            'Text LLM Downloader',
                            DEFAULT_TEXT_MODELS,
                            config.selected_text_model,
                            (val) => setConfig(prev => ({ ...prev, selected_text_model: val })),
                            customTextModel,
                            setCustomTextModel,
                            modelsStatus.text_model
                          )}
                        </div>
                      </div>
                    )}

                    {config.llm_provider === 'ollama' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label">Ollama API URL</label>
                          <input 
                            type="text" 
                            className="text-input" 
                            placeholder="e.g. http://localhost:11434" 
                            value={config.ollama_url || ''}
                            onChange={(e) => setConfig(prev => ({ ...prev, ollama_url: e.target.value }))}
                            onBlur={() => handleSaveConfig()}
                          />
                        </div>

                        {renderRemoteModelSelector(
                          'ollama',
                          config.ollama_url,
                          config.ollama_model,
                          (val) => {
                            setConfig(prev => ({ ...prev, ollama_model: val }));
                            handleSaveConfig({ ...config, ollama_model: val });
                          }
                        )}
                      </div>
                    )}

                    {config.llm_provider === 'openai_compatible' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label">API Base URL</label>
                          <input 
                            type="text" 
                            className="text-input" 
                            placeholder="e.g. http://localhost:1234/v1" 
                            value={config.openai_url || ''}
                            onChange={(e) => setConfig(prev => ({ ...prev, openai_url: e.target.value }))}
                            onBlur={() => handleSaveConfig()}
                          />
                        </div>

                        {renderRemoteModelSelector(
                          'openai_compatible',
                          config.openai_url,
                          config.openai_model,
                          (val) => {
                            setConfig(prev => ({ ...prev, openai_model: val }));
                            handleSaveConfig({ ...config, openai_model: val });
                          }
                        )}
                      </div>
                    )}
                  </div>

                  {/* Image Generation Panel */}
                  <div className="glass-panel" style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', padding: '1.25rem' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
                      <ImageIcon size={18} className="text-accent" />
                      2. Image Generation Model
                    </h3>
                    
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '1rem', lineHeight: '1.4' }}>
                      Storyboard images are always generated locally on your machine using local hardware acceleration or CPU.
                    </p>

                    <div style={{ borderTop: '1px dashed var(--border)', paddingTop: '1rem' }}>
                      {renderModelDownloader(
                        'image',
                        'Image Model Downloader',
                        DEFAULT_IMAGE_MODELS,
                        config.selected_image_model,
                        (val) => setConfig(prev => ({ ...prev, selected_image_model: val })),
                        customImageModel,
                        setCustomImageModel,
                        modelsStatus.image_model
                      )}
                    </div>
                  </div>
                </div>

                {/* Action Buttons bar */}
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {config.llm_provider === 'local' && (
                      <button 
                        className="btn btn-secondary"
                        onClick={() => {
                          const textRepo = customTextModel || config.selected_text_model;
                          const imageRepo = customImageModel || config.selected_image_model;
                          triggerModelDownload(textRepo);
                          triggerModelDownload(imageRepo);
                        }}
                      >
                        <RefreshCw size={14} /> Download/Verify Both Caches
                      </button>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    {!canProceed && (
                      <span style={{ fontSize: '0.85rem', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <AlertCircle size={14} />
                        {!isImageModelReady 
                          ? "The Image Generation model cache must be verified to proceed."
                          : config.llm_provider === 'local'
                            ? "The Text Generation model cache must be verified to proceed."
                            : "Please connect to the local server and select an available model to proceed."}
                      </span>
                    )}
                    
                    <button 
                      className="btn btn-primary" 
                      onClick={() => setActiveStep(2)}
                      disabled={!canProceed}
                      style={{ minWidth: '180px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
                    >
                      Proceed to Script Input <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* STEP 2: SCRIPT INPUT PANEL */}
          {activeStep === 2 && (
            <div>
              <h2 style={{ fontSize: '1.4rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FileText size={20} className="text-primary" />
                Input YouTube script
              </h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
                Enter your YouTube script below. Include timestamps like <code>0:00 - Scene Description</code> for the script analyzer. 
                If timestamps are omitted, the local LLM will automatically segment the scenes for you.
              </p>

              <div className="form-group">
                <textarea 
                  className="text-input textarea-input"
                  placeholder="Paste your script here... e.g.
0:00 - Introduction to the video.
0:05 - A character stands in the center wondering how computers work.
0:10 - He gets hit by a giant lightbulb of inspiration."
                  value={scriptText}
                  onChange={(e) => setScriptText(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', width: '100%' }}>
                <button 
                  className="btn btn-secondary" 
                  onClick={handleLoadSampleScript}
                  disabled={isParsing}
                >
                  Load Sample Script
                </button>
                
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  {isParsing && (
                    <button
                      className="btn btn-secondary"
                      style={{
                        color: '#EF4444',
                        borderColor: 'rgba(239, 68, 68, 0.3)',
                        background: 'rgba(239, 68, 68, 0.05)',
                        margin: 0
                      }}
                      onClick={async () => {
                        try {
                          const res = await fetch('/api/script/cancel', { method: 'POST' });
                          if (res.ok) {
                            showNotification('Script parsing cancel request sent.', 'warning');
                          }
                        } catch (err) {
                          showNotification('Failed to cancel script parsing.', 'danger');
                        }
                      }}
                    >
                      Stop Parsing
                    </button>
                  )}
                  <button 
                    className="btn btn-primary" 
                    onClick={handleParseScript}
                    disabled={isParsing || !scriptText.trim()}
                  >
                    {isParsing ? (
                      <>
                        <Loader size={16} className="spinner" /> Analyzing Script...
                      </>
                    ) : (
                      <>
                        Analyze Script & Generate Visual Prompts <ChevronRight size={16} />
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: PROMPT EDITOR PANEL */}
          {activeStep === 3 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.4rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Edit3 size={20} className="text-primary" />
                    Storyboard prompt editor
                  </h2>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                    Adjust and refine the visual prompts generated by the local LLM. These prompts will be fed into the image generator.
                  </p>
                </div>
                <button 
                  className="btn btn-accent" 
                  onClick={handleStartGeneration}
                  disabled={jobStatus.status === 'running'}
                >
                  <Play size={16} /> Generate All Images
                </button>
              </div>

              {jobStatus.status === 'running' && (
                <div className="glass-panel" style={{ border: '1px solid var(--border-primary)', marginBottom: '1.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                    <span>Generating Storyboard Images...</span>
                    <span>{Math.round(jobStatus.progress)}%</span>
                  </div>
                  <div className="progress-container" style={{ height: '10px' }}>
                    <div className="progress-bar" style={{ width: `${jobStatus.progress}%` }}></div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      Generating scene {jobStatus.current_segment_index + 1} of {jobStatus.total_segments}... This can take 10-30s per image on CPU.
                    </span>
                    <button
                      className="btn btn-secondary"
                      style={{
                        fontSize: '0.8rem',
                        padding: '0.35rem 0.75rem',
                        color: '#EF4444',
                        borderColor: 'rgba(239, 68, 68, 0.3)',
                        background: 'rgba(239, 68, 68, 0.05)',
                        margin: 0
                      }}
                      onClick={async () => {
                        try {
                          const res = await fetch('/api/jobs/cancel', { method: 'POST' });
                          if (res.ok) {
                            showNotification('Image generation cancel request sent.', 'warning');
                          }
                        } catch (err) {
                          showNotification('Failed to cancel image generation.', 'danger');
                        }
                      }}
                    >
                      Stop Generation
                    </button>
                  </div>
                </div>
              )}

              <div className="segments-list">
                {segments.map((segment) => (
                  <div key={segment.id} className="segment-card">
                    <div className="segment-info">
                      <div className="segment-header">
                        <span className="timestamp-badge">{segment.timestamp}</span>
                        {segment.status === 'completed' && <span className="badge badge-success">Completed</span>}
                        {segment.status === 'generating' && <span className="badge badge-warning">Generating</span>}
                        {segment.status === 'failed' && <span className="badge badge-danger">Failed</span>}
                        {segment.status === 'pending' && <span className="badge badge-muted">Pending</span>}
                      </div>
                      
                      <div className="segment-text">
                        "{segment.text}"
                      </div>
                      
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: '0.75rem', marginBottom: '0.25rem' }}>Visual Prompt payload</label>
                        <textarea 
                          className="text-input prompt-textarea"
                          value={segment.visual_prompt}
                          onChange={(e) => handleUpdateSegmentPrompt(segment.id, e.target.value)}
                          disabled={jobStatus.status === 'running'}
                        />
                      </div>
                    </div>
                    
                    <div>
                      <div className="segment-image-container">
                        {segment.image_url ? (
                          <>
                            <img src={segment.image_url} alt="Scene preview" className="segment-image" />
                            <div className="image-overlay">
                              <button className="icon-btn" onClick={() => setFullImageModal(segment.image_url)} title="Zoom In">
                                <ZoomIn size={16} />
                              </button>
                            </div>
                          </>
                        ) : segment.status === 'generating' ? (
                          <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-secondary)' }}>
                            <Loader size={24} className="spinner text-accent" style={{ marginBottom: '0.5rem' }} />
                            <div style={{ fontSize: '0.8rem' }}>Generating...</div>
                          </div>
                        ) : (
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: '1rem' }}>
                            <ImageIcon size={20} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
                            <div>No image generated</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* STEP 4: STORYBOARD OUTPUT VIEW */}
          {activeStep === 4 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.4rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <CheckCircle size={20} className="text-success" />
                    Storyboard output
                  </h2>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                    All scenes generated successfully. Review the full storyboard storyboard below.
                  </p>
                </div>
                
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button className="btn btn-secondary" onClick={() => setActiveStep(3)}>
                    Edit Prompts / Regenerate
                  </button>
                  <button className="btn btn-accent" onClick={handleDownloadZip} disabled={isDownloadingZip}>
                    {isDownloadingZip ? <Loader size={16} className="spinner" /> : <FolderDown size={16} />}
                    Download ZIP Storyboard
                  </button>
                </div>
              </div>

              <div className="output-grid">
                {segments.map((segment) => (
                  <div key={segment.id} className="output-card">
                    <div className="segment-image-container" style={{ borderRadius: 0 }}>
                      {segment.image_url ? (
                        <>
                          <img src={segment.image_url} alt="Scene image" className="segment-image" />
                          <div className="image-overlay">
                            <button className="icon-btn" onClick={() => setFullImageModal(segment.image_url)}>
                              <ZoomIn size={16} />
                            </button>
                            <a href={segment.image_url} download={`scene_${segment.timestamp}.png`} className="icon-btn" title="Download scene">
                              <FolderDown size={16} />
                            </a>
                          </div>
                        </>
                      ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No image</div>
                      )}
                    </div>
                    <div className="output-info">
                      <span className="timestamp-badge" style={{ marginBottom: '0.5rem', display: 'inline-block' }}>
                        {segment.timestamp}
                      </span>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontStyle: 'italic', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        "{segment.text}"
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
        </main>
      </div>

      {/* Real-time Console Log Terminal */}
      {renderTerminalWindow()}

      {/* Expanded Image Modal */}
      {fullImageModal && (
        <div className="modal-overlay" onClick={() => setFullImageModal(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '80vw' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: '1.1rem' }}>Scene Preview</h3>
              <button className="icon-btn" onClick={() => setFullImageModal(null)} style={{ fontSize: '1.2rem', padding: '0.2rem' }}>×</button>
            </div>
            <div className="modal-body" style={{ display: 'flex', justifyContent: 'center', background: '#000', padding: 0 }}>
              <img src={fullImageModal} alt="Expanded preview" style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
