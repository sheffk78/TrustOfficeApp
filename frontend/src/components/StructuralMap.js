import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

const ENTITY_COLORS = {
  'Trust': { bg: '#010079', text: '#FFFFFF', border: '#010079' },
  'Holding LLC': { bg: '#1e3a5f', text: '#FFFFFF', border: '#1e3a5f' },
  'Operating LLC': { bg: '#4a7c59', text: '#FFFFFF', border: '#4a7c59' },
  'Corporation': { bg: '#7c3a1e', text: '#FFFFFF', border: '#7c3a1e' },
  'Partnership': { bg: '#5f1e5f', text: '#FFFFFF', border: '#5f1e5f' },
};

const RELATIONSHIP_COLORS = {
  'owns': '#010079',
  'controls': '#1e3a5f',
  'receives_distributions_from': '#4a7c59',
  'pays_compensation_to': '#7c3a1e',
};

function formatRelType(type) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function StructuralMap({ entities = [], relationships = [] }) {
  const navigate = useNavigate();
  const handleNodeClick = useCallback((_, node) => {
    if (node?.id) {
      navigate(`/entities/${node.id}`);
    }
  }, [navigate]);

  const { nodes, edges } = useMemo(() => {
    if (entities.length === 0) return { nodes: [], edges: [] };

    // Build nodes from entities
    const nodeList = entities.map((entity, index) => {
      const colors = ENTITY_COLORS[entity.entity_type] || ENTITY_COLORS['Trust'];
      return {
        id: entity.entity_id,
        type: 'default',
        data: {
          label: (
            <div className="flex flex-col items-center gap-1 cursor-pointer">
              <span className="font-semibold text-xs">{entity.name}</span>
              <span className="text-[10px] opacity-80">{entity.entity_type}</span>
            </div>
          ),
        },
        position: { x: 0, y: 0 },
        style: {
          background: colors.bg,
          color: colors.text,
          border: `2px solid ${colors.border}`,
          borderRadius: '8px',
          padding: '8px 12px',
          fontSize: '12px',
          fontWeight: '600',
          minWidth: '120px',
          maxWidth: '200px',
          textAlign: 'center',
          cursor: 'pointer',
        },
        className: 'cursor-pointer hover:opacity-80 transition-opacity',
      };
    });

    // Auto-layout: find root entities (no parent), then lay out tree
    const childIds = new Set(relationships.map(r => r.child_entity_id));
    const rootEntities = entities.filter(e => !childIds.has(e.entity_id));
    
    // Simple tree layout
    const nodePositions = {};
    const HORIZONTAL_SPACING = 260;
    const VERTICAL_SPACING = 120;
    
    // Position roots at top
    rootEntities.forEach((entity, index) => {
      nodePositions[entity.entity_id] = {
        x: index * HORIZONTAL_SPACING,
        y: 0,
      };
    });

    // BFS to position children
    const queue = [...rootEntities.map(e => e.entity_id)];
    const visited = new Set();
    while (queue.length > 0) {
      const parentId = queue.shift();
      if (visited.has(parentId)) continue;
      visited.add(parentId);
      
      const children = relationships
        .filter(r => r.parent_entity_id === parentId)
        .map(r => r.child_entity_id);
      
      const parentPos = nodePositions[parentId] || { x: 0, y: 0 };
      const startX = parentPos.x - ((children.length - 1) * HORIZONTAL_SPACING) / 2;
      
      children.forEach((childId, index) => {
        if (!nodePositions[childId]) {
          nodePositions[childId] = {
            x: startX + index * HORIZONTAL_SPACING,
            y: parentPos.y + VERTICAL_SPACING,
          };
        }
        queue.push(childId);
      });
    }

    // Position any unpositioned entities
    let offsetX = 0;
    entities.forEach(entity => {
      if (!nodePositions[entity.entity_id]) {
        nodePositions[entity.entity_id] = {
          x: offsetX,
          y: VERTICAL_SPACING * 2,
        };
        offsetX += HORIZONTAL_SPACING;
      }
    });

    // Apply positions to nodes
    nodeList.forEach(node => {
      const pos = nodePositions[node.id] || { x: 0, y: 0 };
      node.position = pos;
    });

    // Build edges from relationships
    const edgeList = relationships.map((rel, index) => ({
      id: `e-${index}`,
      source: rel.parent_entity_id,
      target: rel.child_entity_id,
      label: `${formatRelType(rel.relationship_type)}${rel.ownership_percentage ? ` (${rel.ownership_percentage}%)` : ''}`,
      type: 'smoothstep',
      animated: rel.relationship_type === 'owns',
      style: {
        stroke: RELATIONSHIP_COLORS[rel.relationship_type] || '#666',
        strokeWidth: 2,
      },
      labelStyle: {
        fontSize: '10px',
        fontWeight: '600',
        fill: '#333',
      },
      labelBgStyle: {
        fill: '#fff',
        fillOpacity: 0.9,
      },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: RELATIONSHIP_COLORS[rel.relationship_type] || '#666',
      },
    }));

    return { nodes: nodeList, edges: edgeList };
  }, [entities, relationships]);

  if (entities.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Create entities and relationships to see the structural map
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '400px' }} className="rounded border border-border">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={1.5}
        attributionPosition="bottom-left"
      >
        <Controls showInteractive={false} />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
          style={{ background: '#f8fafc' }}
        />
        <Background variant="dots" gap={16} size={1} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}