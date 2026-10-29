import { useState } from 'react';
import { Navigation, Compass } from 'lucide-react';

export interface RoomNode {
  id: string;
  name: string;
  x: number;
  y: number;
  description: string;
  connections: string[];
  threat_level?: string;
}

const DEFAULT_ROOMS: RoomNode[] = [
  {
    id: "woods",
    name: "Misty Svalich Woods",
    x: 60,
    y: 180,
    description: "Cold fog rolls between towering pine trees. Raven calls echo through the darkness.",
    connections: ["gates"],
    threat_level: "Low"
  },
  {
    id: "gates",
    name: "Wrought Iron Gates",
    x: 180,
    y: 180,
    description: "Massive rusted iron gates flanked by stone gargoyles that seem to turn their heads.",
    connections: ["woods", "foyer"],
    threat_level: "Moderate"
  },
  {
    id: "foyer",
    name: "Grand Foyer",
    x: 300,
    y: 180,
    description: "A drafty entrance hall paneled in dark oak. A suit of blackened plate armor stands sentry.",
    connections: ["gates", "dining", "conservatory"],
    threat_level: "Low"
  },
  {
    id: "dining",
    name: "Cursed Dining Hall",
    x: 300,
    y: 80,
    description: "A crystal chandelier hangs above a banquet table set for a feast that never began.",
    connections: ["foyer", "attic"],
    threat_level: "High"
  },
  {
    id: "conservatory",
    name: "Sunken Conservatory",
    x: 300,
    y: 280,
    description: "Overgrown dead ferns and rotting tapestries. The distant sound of crying children echoes here.",
    connections: ["foyer", "dungeon_stairs"],
    threat_level: "Moderate"
  },
  {
    id: "attic",
    name: "Locked Attic & Crib",
    x: 440,
    y: 80,
    description: "Dust motes dance in moonlight filtering through boarded windows. Two small spirits weep in the corner.",
    connections: ["dining", "dungeon_stairs"],
    threat_level: "High"
  },
  {
    id: "dungeon_stairs",
    name: "Spiral Dungeon Stairs",
    x: 440,
    y: 280,
    description: "Narrow, slippery stone steps descending into damp darkness smelling of decay and sulfur.",
    connections: ["conservatory", "attic", "altar"],
    threat_level: "Severe"
  },
  {
    id: "altar",
    name: "The Relic Altar Chamber",
    x: 580,
    y: 200,
    description: "A sunken stone dais inscribed with ancient runes. Chanting whispers pulse through the floorboards.",
    connections: ["dungeon_stairs"],
    threat_level: "Deadly"
  }
];

interface DungeonMapProps {
  onTravelToRoom: (roomName: string) => void;
}

export default function DungeonMap({ onTravelToRoom }: DungeonMapProps) {
  const [rooms] = useState<RoomNode[]>(DEFAULT_ROOMS);
  const [currentRoomId, setCurrentRoomId] = useState<string>("woods");
  const [visitedRooms, setVisitedRooms] = useState<Set<string>>(new Set(["woods", "gates"]));
  const [selectedRoom, setSelectedRoom] = useState<RoomNode>(DEFAULT_ROOMS[0]);

  const currentRoom = rooms.find(r => r.id === currentRoomId) || rooms[0];

  const handleRoomClick = (room: RoomNode) => {
    setSelectedRoom(room);
  };

  const handleTravel = (room: RoomNode) => {
    setCurrentRoomId(room.id);
    setSelectedRoom(room);
    setVisitedRooms(prev => new Set([...prev, room.id]));
    onTravelToRoom(room.name);
  };

  const isConnected = currentRoom.connections.includes(selectedRoom.id);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-secondary)' }}>
      {/* Map Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--gold)', fontWeight: 700, fontSize: '0.9rem' }}>
          <Compass size={16} />
          <span>DUNGEON EXPLORER</span>
        </div>
        <div style={{ fontSize: '0.75rem', color: '#8b92a5' }}>
          Current: <strong style={{ color: '#fff' }}>{currentRoom.name}</strong>
        </div>
      </div>

      {/* SVG Interactive Map Canvas */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#08090c' }}>
        <svg
          viewBox="0 0 680 360"
          style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.6))' }}
        >
          {/* Corridors / Connection Lines */}
          {rooms.map(room => {
            return room.connections.map(targetId => {
              const target = rooms.find(r => r.id === targetId);
              if (!target || room.id > target.id) return null; // Avoid drawing duplicate lines

              const isKnown = visitedRooms.has(room.id) || visitedRooms.has(target.id);

              return (
                <line
                  key={`${room.id}-${target.id}`}
                  x1={room.x}
                  y1={room.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={isKnown ? '#384055' : '#1a1d26'}
                  strokeWidth={isKnown ? 3 : 1.5}
                  strokeDasharray={isKnown ? undefined : "4 4"}
                />
              );
            });
          })}

          {/* Room Nodes */}
          {rooms.map(room => {
            const isVisited = visitedRooms.has(room.id);
            const isCurrent = currentRoomId === room.id;
            const isSelected = selectedRoom.id === room.id;
            const isAdjacent = currentRoom.connections.includes(room.id);

            let nodeColor = "#1e2230";
            let borderColor = "#384055";

            if (isCurrent) {
              nodeColor = "#d4af37";
              borderColor = "#fff";
            } else if (isSelected) {
              nodeColor = "#457b9d";
              borderColor = "#a8dadc";
            } else if (isAdjacent) {
              borderColor = "#2a9d8f";
            } else if (!isVisited) {
              nodeColor = "#11131a";
              borderColor = "#202430";
            }

            return (
              <g
                key={room.id}
                onClick={() => handleRoomClick(room)}
                style={{ cursor: 'pointer', transition: 'all 0.2s' }}
              >
                {/* Glow ring on current player location */}
                {isCurrent && (
                  <circle
                    cx={room.x}
                    cy={room.y}
                    r={22}
                    fill="none"
                    stroke="#d4af37"
                    strokeWidth={2}
                    opacity={0.4}
                    style={{ animation: 'pulse 1.8s infinite' }}
                  />
                )}

                {/* Main Room Node Circle */}
                <circle
                  cx={room.x}
                  cy={room.y}
                  r={15}
                  fill={nodeColor}
                  stroke={borderColor}
                  strokeWidth={isSelected || isCurrent ? 2.5 : 1.5}
                />

                {/* Icon or Marker inside circle */}
                {isCurrent && (
                  <circle cx={room.x} cy={room.y} r={5} fill="#000" />
                )}

                {/* Room Label */}
                <text
                  x={room.x}
                  y={room.y + 26}
                  textAnchor="middle"
                  fill={isVisited || isAdjacent ? "#e2e4ec" : "#555b6e"}
                  fontSize="10"
                  fontFamily="sans-serif"
                  fontWeight={isCurrent || isSelected ? "bold" : "normal"}
                >
                  {isVisited || isAdjacent ? room.name : "???"}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Selected Room Detail Drawer */}
      <div style={{ padding: '14px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg-card)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h4 style={{ color: '#fff', fontSize: '0.95rem' }}>{selectedRoom.name}</h4>
            <span style={{ fontSize: '0.7rem', color: selectedRoom.threat_level === 'Deadly' ? '#ff6b6b' : '#2a9d8f' }}>
              Threat: {selectedRoom.threat_level || 'Unknown'}
            </span>
          </div>

          {selectedRoom.id !== currentRoomId && (
            <button
              onClick={() => handleTravel(selectedRoom)}
              disabled={!isConnected}
              className="send-btn"
              style={{
                padding: '6px 12px',
                fontSize: '0.75rem',
                opacity: isConnected ? 1 : 0.5,
                cursor: isConnected ? 'pointer' : 'not-allowed'
              }}
            >
              <Navigation size={12} />
              <span>{isConnected ? "Travel Here" : "No Direct Path"}</span>
            </button>
          )}
        </div>

        <p style={{ fontSize: '0.8rem', color: '#a0a6b8', marginTop: 8, lineHeight: 1.4 }}>
          {visitedRooms.has(selectedRoom.id) || currentRoom.connections.includes(selectedRoom.id)
            ? selectedRoom.description
            : "This area remains shrouded in thick darkness. Advance into adjacent rooms to scout it."}
        </p>
      </div>
    </div>
  );
}
