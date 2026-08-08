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

  it('still renders the greeting when messages is undefined', () => {
    render(<ChatPanel {...baseProps} messages={undefined} />);
    expect(screen.getByText(/Hi! I'm your Trust Assistant/)).toBeInTheDocument();
  });

  it('renders message bubbles when messages is a real array', () => {
    const messages = [
      { id: 'msg-1', role: 'user', content: 'hello' },
    ];
    render(<ChatPanel {...baseProps} messages={messages} />);
    expect(screen.getAllByTestId('message-bubble').length).toBeGreaterThanOrEqual(1);
  });
});
