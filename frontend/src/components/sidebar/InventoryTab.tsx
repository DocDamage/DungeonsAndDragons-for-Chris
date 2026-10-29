import React from 'react';
import type { Item } from '../../types';

interface InventoryTabProps {
  inventory: Item[];
  onUseItem: (itemName: string) => void;
}

export const InventoryTab: React.FC<InventoryTabProps> = ({ inventory, onUseItem }) => {
  return (
    <div style={{ padding: '12px 16px', flex: 1, overflowY: 'auto' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#8b92a5', marginBottom: 8, textTransform: 'uppercase' }}>
        Equipped & Inventory
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {inventory.map((item, idx) => {
          const isConsumable = item.item_type in ["potion", "consumable"] ||
            item.name.toLowerCase().includes("potion") ||
            item.name.toLowerCase().includes("apple") ||
            item.name.toLowerCase().includes("medpac");

          return (
            <div
              key={idx}
              style={{
                background: '#181b24',
                border: '1px solid #282d3d',
                padding: '8px 10px',
                borderRadius: 4,
                fontSize: '0.85rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <div>
                <span style={{ color: item.equipped ? '#d4af37' : '#e2e4ec' }}>
                  {item.name} {item.quantity > 1 && `(x${item.quantity})`}
                </span>
                {item.damage && (
                  <span style={{ marginLeft: 6, fontSize: '0.75rem', color: '#ff6b6b' }}>
                    [{item.damage}]
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {isConsumable && (
                  <button
                    onClick={() => onUseItem(item.name)}
                    className="hp-btn"
                    style={{ color: '#2a9d8f', borderColor: '#2a9d8f', fontSize: '0.65rem', padding: '1px 5px' }}
                  >
                    Use
                  </button>
                )}
                <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: '#8b92a5' }}>
                  {item.item_type}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
