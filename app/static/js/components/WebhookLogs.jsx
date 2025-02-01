import React, { useState, useEffect } from 'react';
import { Search } from 'lucide-react';

const WebhookLogs = function({ isAdmin }) {
  const [logs, setLogs] = React.useState([]);
  const [searchTerm, setSearchTerm] = React.useState('');
  const [expandedRows, setExpandedRows] = React.useState(new Set());
  const [sortConfig, setSortConfig] = React.useState({
      key: 'timestamp',
      direction: 'desc'
  });

  React.useEffect(() => {
    // Load initial logs
    fetch('/api/logs')
        .then(response => response.json())
        .then(data => {
            console.log('Initial logs received:', data);
            if (Array.isArray(data)) {
                setLogs(data);
            }
        })
        .catch(error => {
            console.error('Error loading initial logs:', error);
        });

    // Set up SSE connection for real-time updates
    const userId = document.querySelector('meta[name="user-id"]').content;
    console.log('Setting up webhook SSE connection for user:', userId);
    
    const evtSource = new EventSource(`/events`);  // Changed from /stream/channel/user_${userId}
    
    evtSource.addEventListener('webhook_update', (event) => {
        console.log('Received webhook update:', event.data);
        try {
            const data = JSON.parse(event.data);
            if (data.logs && Array.isArray(data.logs)) {
                setLogs(data.logs);
            }
        } catch (error) {
            console.error('Error processing webhook update:', error);
        }
    });

    evtSource.onerror = (error) => {
        console.error('SSE Error:', error);
    };

    evtSource.onopen = (e) => {
        console.log('Webhook SSE Connection opened');
    };

    return () => {
        console.log('Cleaning up webhook SSE connection');
        evtSource.close();
    };
  }, []);  // Empty dependency array - only run on mount
    
    evtSource.onmessage = (event) => {
      try {
        const newLogs = JSON.parse(event.data);
        if (Array.isArray(newLogs) && newLogs.length > 0) {
          setLogs(newLogs);
        }
      } catch (error) {
        console.error('Error parsing webhook logs:', error);
      }
    };

    evtSource.onerror = (error) => {
      console.error('SSE Error:', error);
      evtSource.close();
      // Try to reconnect after 5 seconds
      setTimeout(() => {
        setLogs(prevLogs => {
          if (prevLogs.length === 0) {
            new EventSource('/webhook-stream');
          }
          return prevLogs;
        });
      }, 5000);
    };

    return () => evtSource.close();
  }, []);

  const toggleRow = (id) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const getSortedAndFilteredLogs = () => {
    return logs
      .filter(log => {
        const searchStr = searchTerm.toLowerCase();
        return (
          log.automation_name.toLowerCase().includes(searchStr) ||
          JSON.stringify(log.payload).toLowerCase().includes(searchStr)
        );
      })
      .sort((a, b) => {
        const direction = sortConfig.direction === 'asc' ? 1 : -1;
        if (sortConfig.key === 'timestamp') {
          return direction * (new Date(a.timestamp) - new Date(b.timestamp));
        }
        return direction * String(a[sortConfig.key]).localeCompare(String(b[sortConfig.key]));
      });
  };

  return (
    <div className="card">
      <div className="card-header">
        <div className="d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center gap-3">
            <h4 className="mb-0">Webhook Logs</h4>
            <div className="position-relative">
              <Search className="position-absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={16} />
              <input
                type="text"
                placeholder="Search logs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="form-control pl-8"
              />
            </div>
          </div>
        </div>
      </div>
      <div className="card-body p-0 table-responsive">
        <table className="table mb-0">
          <thead>
            <tr>
              <th 
                onClick={() => handleSort('timestamp')}
                className="cursor-pointer"
              >
                Timestamp (UTC)
                {sortConfig.key === 'timestamp' && (
                  <span className="ml-1">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
              <th 
                onClick={() => handleSort('automation_name')}
                className="cursor-pointer"
              >
                Automation
                {sortConfig.key === 'automation_name' && (
                  <span className="ml-1">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            {getSortedAndFilteredLogs().map((log) => (
              <tr 
                key={`${log.timestamp}-${log.automation_name}`}
                className={`webhook-type-${(log.payload?.action || '').toLowerCase() || 'other'}`}
                onClick={() => toggleRow(`${log.timestamp}-${log.automation_name}`)}
              >
                <td>{new Date(log.timestamp).toLocaleString()}</td>
                <td>{log.automation_name}</td>
                <td className="position-relative">
                  {expandedRows.has(`${log.timestamp}-${log.automation_name}`) ? (
                    <pre className="mb-0 white-space-pre-wrap">{JSON.stringify(log.payload, null, 2)}</pre>
                  ) : (
                    <pre className="mb-0 text-truncate">{JSON.stringify(log.payload)}</pre>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default WebhookLogs;