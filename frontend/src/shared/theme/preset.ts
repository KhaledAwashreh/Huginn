import { definePreset } from '@primeuix/themes';
import Aura from '@primeuix/themes/aura';

export const huginnPreset = definePreset(Aura, {
  primitive: {
    green: {
      50: '#effaf3',
      100: '#d9f2e2',
      200: '#b6e5c8',
      300: '#84d1a5',
      400: '#4bb67b',
      500: '#23965b',
      600: '#167b49',
      700: '#12613c',
      800: '#124d33',
      900: '#103f2b',
      950: '#082319',
    },
  },
  semantic: {
    primary: {
      50: '{green.50}',
      100: '{green.100}',
      200: '{green.200}',
      300: '{green.300}',
      400: '{green.400}',
      500: '{green.500}',
      600: '{green.600}',
      700: '{green.700}',
      800: '{green.800}',
      900: '{green.900}',
      950: '{green.950}',
    },
    colorScheme: {
      light: {
        formField: {
          borderColor: '#52645a',
          hoverBorderColor: '#12613c',
          focusBorderColor: '#12613c',
        },
        primary: {
          color: '{primary.700}',
          contrastColor: '#ffffff',
          hoverColor: '{primary.800}',
          activeColor: '{primary.900}',
        },
        highlight: {
          background: '{primary.50}',
          focusBackground: '{primary.100}',
          color: '{primary.800}',
          focusColor: '{primary.900}',
        },
      },
    },
  },
});
