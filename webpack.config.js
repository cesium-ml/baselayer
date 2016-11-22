const webpack = require('webpack');
const path = require('path');

const config = {
  entry: path.resolve(__dirname, 'public/scripts/main.jsx'),
  output: {
    path: path.resolve(__dirname, 'public/build'),
    filename: 'bundle.js'
  },
  resolve: {
    extensions: ['', '.js', '.jsx']
  }
};

module.exports = config;
