import React from 'react';
import { X } from 'lucide-react';

interface ImageLightboxModalProps {
  imageUrl: string;
  onClose: () => void;
}

export const ImageLightboxModal: React.FC<ImageLightboxModalProps> = ({
  imageUrl,
  onClose
}) => {
  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <img
        src={imageUrl}
        alt="Illustrated Scene"
        className="lightbox-content"
        onClick={(e) => e.stopPropagation()}
      />
      <button
        onClick={onClose}
        className="hp-btn"
        style={{
          position: 'fixed',
          top: 20,
          right: 20,
          padding: 8,
          background: 'rgba(0,0,0,0.8)',
          border: '1px solid var(--gold)'
        }}
        title="Close Lightbox"
      >
        <X size={20} color="#d4af37" />
      </button>
    </div>
  );
};
