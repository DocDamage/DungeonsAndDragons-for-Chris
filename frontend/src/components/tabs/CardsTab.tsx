import React from 'react';
import type { StoryCard } from '../../types';

interface CardsTabProps {
  cards: StoryCard[];
}

export const CardsTab: React.FC<CardsTabProps> = ({ cards }) => {
  return (
    <div className="cards-list">
      <div style={{ fontSize: '0.75rem', color: '#8b92a5', marginBottom: 4 }}>
        Story Cards are dynamically injected into context when keywords match recent dialogue:
      </div>
      {cards.map((card) => (
        <div key={card.id} className="card-item">
          <div className="card-item-title">
            <span>{card.title}</span>
            <span className="card-badge">{card.card_type}</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: '#d4af37', marginTop: 2 }}>
            Keys: {card.keys.slice(0, 3).join(", ")}
          </div>

          {card.image_url && (
            <img
              src={card.image_url}
              alt={card.title}
              className="card-image-preview"
            />
          )}

          <div className="card-snippet">{card.entry}</div>
        </div>
      ))}
    </div>
  );
};
