import React from 'react';
import { render, screen } from '@testing-library/react';
import ChatPanel from '@/components/ChatPanel';

// Mock heavy child components so the test targets ChatPanel's own logic,
// not MessageBubble/FileUploadCard's dependency trees (react-markdown, etc.)
jest.mock('@/components/MessageBubble', () => {
  return function MockMessageBubble({ message }) {
    return <div data-testid="message-bubble">{String(message?.content || message?.id || 'msg')}</div>;
  };
});
jest.mock('@/components/FileUploadCard', () => {
  return function MockFileUploadCard() {
    return <div data-testid="file-upload-card" />;
  };
});

const baseProps = {
  loading: false,
  error: null,
  isStreaming: false,
  streamPhase: null,
  onSendMessage: jest.fn(),
  onStopStreaming: jest.fn(),
  onClearError: jest.fn(),
  onNewChat: jest.fn(),
  onActionApprove: jest.fn(),
  onActionEdit: jest.fn(),
  onActionDiscard: jest.fn(),
  onVideoClick: jest.fn(),
  loadingConversation: false,
  trustId: 'trust_1',
  onFileUploaded: jest.fn(),
};

describe('ChatPanel regression: messages may be undefined', () => {
  // Bug: "undefined is not an object (evaluating 't.length')" — the component
  // called messages.length / messages.some / [...messages] directly while the
  // parent could pass `messages` as undefined during conversation switch/load.
  it('does not throw when messages is undefined', () => {
    expect(() =>
      render(<ChatPanel {...baseProps} messages={undefined} />)
    ).not.toThrow();
  });

  it('still renders the empty-state welcome when messages is undefined', () => {
    // Greeting bubble was replaced (82a9551) by the welcome heading + chips empty state
    render(<ChatPanel {...baseProps} messages={undefined} />);
    expect(screen.getByText('Trust Assistant')).toBeInTheDocument();
  });

  it('renders message bubbles when messages is a real array', () => {
    const messages = [
      { id: 'msg-1', role: 'user', content: 'hello' },
    ];
    render(<ChatPanel {...baseProps} messages={messages} />);
    expect(screen.getAllByTestId('message-bubble').length).toBeGreaterThanOrEqual(1);
  });
});

describe('ChatPanel WingPoint empty state (2026-10-30)', () => {
  const chipLabels = () =>
    screen.queryAllByRole('button').map((b) => b.textContent);

  it('shows the WingPoint subline + WP chips for a wingpoint-sourced trust', () => {
    render(
      <ChatPanel
        {...baseProps}
        messages={undefined}
        activeTrust={{ trust_id: 't_wp', source: 'wingpoint' }}
      />
    );
    expect(screen.getByText(/This trust came from WingPoint/)).toBeInTheDocument();
    const labels = chipLabels();
    expect(labels.some((t) => t.includes('WingPoint Training'))).toBe(true);
    expect(labels.some((t) => t.includes('508 Tax Status'))).toBe(true);
    expect(labels.some((t) => t.includes('508 Money Flow'))).toBe(true);
    // Standard chips are hidden on the WP empty state
    expect(labels.some((t) => t.includes('Check Deadlines'))).toBe(false);
  });

  it('shows the WingPoint subline for a trust carrying wingpoint_ref', () => {
    render(
      <ChatPanel
        {...baseProps}
        messages={undefined}
        activeTrust={{ trust_id: 't_ref', wingpoint_ref: 'wp-abc' }}
      />
    );
    expect(screen.getByText(/This trust came from WingPoint/)).toBeInTheDocument();
  });

  it('renders the standard empty state for standard trusts (no WP text, no WP chips)', () => {
    render(
      <ChatPanel
        {...baseProps}
        messages={undefined}
        activeTrust={{ trust_id: 't_std' }}
      />
    );
    expect(screen.getByText(/Ask about deadlines/)).toBeInTheDocument();
    expect(screen.queryByText(/This trust came from WingPoint/)).toBeNull();
    expect(chipLabels().some((t) => t.includes('508 Tax Status'))).toBe(false);
  });

  it('renders the standard empty state when no trust doc rides in (back-compat)', () => {
    render(<ChatPanel {...baseProps} messages={undefined} />);
    expect(screen.getByText(/Ask about deadlines/)).toBeInTheDocument();
    expect(screen.queryByText(/This trust came from WingPoint/)).toBeNull();
  });

  it('standard chips fill the input via onSendMessage when clicked', () => {
    const onSendMessage = jest.fn();
    render(
      <ChatPanel
        {...baseProps}
        messages={undefined}
        onSendMessage={onSendMessage}
        activeTrust={{ trust_id: 't_wp', source: 'wingpoint' }}
      />
    );
    const chip = screen.getByText('508 Tax Status');
    chip.click();
    expect(onSendMessage).toHaveBeenCalledWith("Explain my trust's 508 tax status");
  });
});
