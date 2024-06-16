import * as React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Provider, DefaultTheme } from 'react-native-paper';
import { NavigationContainer, useNavigationContainerRef } from '@react-navigation/native';
import { createMaterialBottomTabNavigator } from '@react-navigation/material-bottom-tabs';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';

import CamaraFotoScreen from './CamaraFoto';
import CamaraVideoScreen from './CamaraVideo';

const Tab = createMaterialBottomTabNavigator();

const App = () => {
  const barColors = {
    camara: 'black',
    video: 'black',
  };

  const [tab, setTab] = React.useState<keyof typeof barColors>('camara');
  const [loadingAnim, setLoadingAnim] = React.useState(false);
  const navRef = useNavigationContainerRef();

  React.useEffect(() => {
    const unsubscribe = navRef.addListener('state', () => {
      const currRoute = navRef.getCurrentRoute();
      if (currRoute) {
        setTimeout(() => setTab(currRoute.name as keyof typeof barColors), 80);
      }
    });
    return unsubscribe;
  });



  return (
    <NavigationContainer ref={navRef}>
      <View style={{ flex: 1 }}>
      
        <Tab.Navigator
          initialRouteName="camara"
          shifting={true}
          activeColor="#e91e63"
          barStyle={{
            backgroundColor: barColors[tab],
          }}>
          <Tab.Screen
            name="camara"
            component={CamaraFotoScreen}
            options={{
              tabBarColor: barColors.camara,
              tabBarLabel: 'Camara',
              tabBarIcon: ({ color }) => (
                <MaterialCommunityIcons name="camera" color={color} size={28} />
              ),
            }}
          />
          <Tab.Screen
            name="video"
            component={CamaraVideoScreen}
            options={{
              tabBarColor: barColors.video,
              tabBarLabel: 'Video',
              tabBarIcon: ({ color }) => (
                <MaterialCommunityIcons name="video" color={color} size={28} />
              ),
            }}
          />
        </Tab.Navigator>
        {loadingAnim && <View style={styles.overlay} />}
        
      </View>
    </NavigationContainer>
  );
};

const theme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    secondaryContainer: 'transparent',
  },
};

export default function Main() {
  return (
    <Provider theme={theme}>
      <App />
    </Provider>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)', // Color oscuro semitransparente
  },
});