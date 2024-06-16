import React, { useState } from 'react';
import { View, ScrollView, Modal as RNModal, StyleSheet, Image, ImageBackground, Alert, PermissionsAndroid } from 'react-native';
import { Button, Text, Provider, ActivityIndicator, DefaultTheme, Card, TouchableRipple } from 'react-native-paper';
import * as ImagePicker from 'react-native-image-picker';


export default function CamaraFotoScreen() {

  const [modalVisible, setModalVisible] = useState(false);
  const [loadingAnim, setLoadingAnim] = useState(false);
  
  const [showMovieDetails, setShowMovieDetails] = useState(false);
  const [backCount, setBackCount] = useState(0)

  const [results, setResults] = useState([]);
  const [selectedActor, setSelectedActor] = useState(null);


  const take_picture = async () => {
    if (loadingAnim) {
      return;
    }

    try {
      let isCameraPermitted = await requestCameraPermission();
      

      if (isCameraPermitted) {
        const response = await ImagePicker.launchCamera({ mediaType: 'photo', quality: 1 })
        if (response.didCancel) {
          return;
        }
        if (!response.cancelled && response.assets && response.assets.length > 0) {
          setLoadingAnim(true); // Activar animación de carga
          await recognizeFaces(response);
        }
      }
    } catch (error) {
      Alert.alert("Error", "Ocurrio un problema al seleccionar la imagen, intentelo de nuevo.")
      console.error('Error al seleccionar imagen:');
    }

  }


  const pickImage = async () => {
    if (loadingAnim) {
      return;
    }
    try {

        const response = await ImagePicker.launchImageLibrary({mediaType: 'photo', quality: 1});

        if (!response.cancelled && response.assets && response.assets.length > 0) {

          setLoadingAnim(true); // Activar animación de carga
          await recognizeFaces(response);

        }
      } catch (error) {
        Alert.alert("Lo sentimos", "No pudimos encontrar ese rostro :(")
    }
  };

  const handleActorCardPress = (actor) => {
    setSelectedActor(actor);
    setShowMovieDetails(true); // Mostramos los detalles de la carta seleccionada
    setBackCount(0);
  };

  const handleBackButtonPress = () => {
    setShowMovieDetails(false);
    setBackCount(backCount+1);
    if (backCount === 2){
      setModalVisible(false);
      setBackCount(0);
    }
  };


  const recognizeFaces = async (image) => {
    console.log("image data: ", image)
    try {
        let formData = new FormData();
        formData.append('file', {
          uri: image.assets[0].uri,
          name: image.assets[0].fileName,
          type: image.assets[0].type,
        });
        console.log("formdata: ", formData)
        const response = await fetch('https://apimodular-iyzgamygbq-wm.a.run.app/photo_recognition', {
          method: 'POST',
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          body: formData,
        });

        if (response.ok) {
          const responseData = await response.json();
          console.log(responseData);
        
          if (Array.isArray(responseData) && responseData.length > 0) {
            setResults(responseData);
            setModalVisible(true);
          } else {
            Alert.alert("Lo sentimos", "No pudimos encontrar ese rostro :(")
            //console.error('La respuesta del servidor no contiene resultados válidos.');
          }
        } else {
          Alert.alert("Error", "La respuesta del servidor no contiene resultados válidos.")
          //console.error('Error en la respuesta del servidor:');
        }
      } catch (error) {
        Alert.alert("Error", "Error al enviar la imagen")
        //console.error('Error al reconocer caras:');
      } finally {
        setLoadingAnim(false); // Desactivar animación de carga
      }
  };

  const requestCameraPermission = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.CAMERA,
          {
            title: 'Permisos de camara',
            message: 'La aplicacion necesita permisos para acceder a la camara.',
          },
        );
        // If CAMERA Permission is granted
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn(err);
        return false;
      }
    } else return true;
  };



  return (
    <ImageBackground source={require('../ActIA/Logo/logo.jpg')} style={styles.backg}>
      <Provider theme={theme}>
        <View style={{ flex: 1, justifyContent: 'center'}}>
          <Button mode="contained" onPress={take_picture} disabled={loadingAnim} style={{marginTop: 20}} >Tomar Foto</Button>
          <Button mode="elevated" onPress={pickImage} disabled={loadingAnim} style={{marginTop: 20}}>Seleccionar Imagen</Button>
          <ActivityIndicator animating={loadingAnim} size={"large"} />
          {loadingAnim && <View style={styles.overlay} />}
        </View>
        <RNModal
          animationType="slide"
          transparent={false}
          visible={modalVisible}
          onRequestClose={handleBackButtonPress}>
          <View style={{ flex: 1, backgroundColor: '#171717'}}>
            <ScrollView>
              {showMovieDetails ? (
                <View style={{ marginBottom: 20 }}>
                  <Image source={{ uri: 'https://image.tmdb.org/t/p/w600_and_h900_bestv2' + selectedActor.profile_path }} style={styles.profileImage} />
                  <Text style={{ fontSize: 18, fontWeight: 'bold', color: 'white', marginBottom: 10, textAlign: 'center' }}>{selectedActor.name}</Text>
                  <Text style={{ color: 'white', textAlign: 'justify', paddingHorizontal: 10 }}>{selectedActor.biography}</Text>
                  {selectedActor.known_for && selectedActor.known_for.map((movie, movieIndex) => (
                    <View key={movieIndex} style={{ marginTop: 10 }}>
                      <Image source={{ uri: 'https://image.tmdb.org/t/p/w600_and_h900_bestv2' + movie.poster_path }} style={styles.posterImage} resizeMode="cover" />
                      <Text style={{ fontSize: 16, fontWeight: 'bold', color: 'white' }}>{movie.title}</Text>
                      <Text style={{ color: 'white', textAlign: 'justify', marginBottom: 10 }}>{movie.overview}</Text>
                    </View>
                  ))}
                </View>
              ) : (
                <ScrollView>
                  {results && Array.isArray(results) && results.map((result, index) => (
                    <View key={index} style={{ width: '100%', paddingHorizontal: 15 }}>
                      <TouchableRipple onPress={() => handleActorCardPress(result)}>
                        <Card style={{ marginBottom: 20, marginTop: 20 }}>
                          <Card.Cover source={{ uri: 'https://image.tmdb.org/t/p/w600_and_h900_bestv2' + result.profile_path }} />
                          <Card.Content>
                            <Text style={{ fontSize: 18, fontWeight: 'bold', color: 'black', marginTop: 10 }}>{result.name}</Text>
                          </Card.Content>
                        </Card>
                      </TouchableRipple>
                    </View>
                  ))}
                  
                </ScrollView>
              )}
            </ScrollView>
            <Button mode='elevated' style={{width: '100%', bottom: 10, position: 'absolute'}} onPress={() => setModalVisible(false)}>Cerrar</Button>          
          </View>
        </RNModal>
      </Provider>
    </ImageBackground>
  );
}

const theme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    secondaryContainer: 'transparent',
  },
};

const styles = StyleSheet.create({
  profileImage: {
    width: 150,
    height: 150, 
    borderRadius: 75, 
    alignSelf: 'center',
  },
  posterImage: {
    width: 'auto',
    height: 200,
    borderRadius: 10,
    marginBottom: 10,
    alignSelf: 'stretch',
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  backg: {
    flex: 1,
    justifyContent: 'center',
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },

});
