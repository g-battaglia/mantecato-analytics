declare module "react-simple-maps" {
  import { ComponentType, CSSProperties, ReactNode, SVGProps } from "react";

  export interface ComposableMapProps {
    projection?: string;
    projectionConfig?: {
      rotate?: [number, number, number];
      center?: [number, number];
      scale?: number;
      parallels?: [number, number];
    };
    width?: number;
    height?: number;
    style?: CSSProperties;
    className?: string;
    children?: ReactNode;
  }

  export interface ZoomableGroupProps {
    center?: [number, number];
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    translateExtent?: [[number, number], [number, number]];
    onMoveStart?: (position: { coordinates: [number, number]; zoom: number }) => void;
    onMove?: (position: { coordinates: [number, number]; zoom: number }) => void;
    onMoveEnd?: (position: { coordinates: [number, number]; zoom: number }) => void;
    children?: ReactNode;
  }

  export interface GeographiesProps {
    geography: string | Record<string, unknown>;
    parseGeographies?: (geos: GeographyObject[]) => GeographyObject[];
    children: (data: { geographies: GeographyObject[] }) => ReactNode;
  }

  export interface GeographyObject {
    id: string;
    rsmKey: string;
    type: string;
    properties: Record<string, string>;
    geometry: Record<string, unknown>;
    svgPath: string;
  }

  export interface GeographyStyleProps {
    default?: CSSProperties;
    hover?: CSSProperties;
    pressed?: CSSProperties;
  }

  export interface GeographyProps extends Omit<SVGProps<SVGPathElement>, "style"> {
    geography: GeographyObject;
    style?: GeographyStyleProps;
  }

  export interface MarkerProps extends SVGProps<SVGGElement> {
    coordinates: [number, number];
    children?: ReactNode;
  }

  export interface SphereProps extends SVGProps<SVGCircleElement> {}

  export interface GraticuleProps extends SVGProps<SVGPathElement> {
    step?: [number, number];
  }

  export const ComposableMap: ComponentType<ComposableMapProps>;
  export const ZoomableGroup: ComponentType<ZoomableGroupProps>;
  export const Geographies: ComponentType<GeographiesProps>;
  export const Geography: ComponentType<GeographyProps>;
  export const Marker: ComponentType<MarkerProps>;
  export const Sphere: ComponentType<SphereProps>;
  export const Graticule: ComponentType<GraticuleProps>;
  export const MapContext: React.Context<unknown>;
  export const MapProvider: ComponentType<{ children?: ReactNode }>;
  export const ZoomPanContext: React.Context<unknown>;
  export const ZoomPanProvider: ComponentType<{ children?: ReactNode }>;

  export function useGeographies(props: { geography: string | Record<string, unknown> }): {
    geographies: GeographyObject[];
  };
  export function useMapContext(): unknown;
  export function useZoomPan(): unknown;
  export function useZoomPanContext(): unknown;
}
