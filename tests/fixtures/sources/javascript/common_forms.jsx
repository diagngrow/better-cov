function declared() {
  return 1;
}

async function load() {
  return Promise.resolve(2);
}

function* identifiers() {
  yield 3;
}

const doubled = (value) => {
  return value * 2;
};

class Worker {
  run() {
    return doubled(2);
  }

  static async build() {
    return new Worker();
  }
}

const helpers = {
  format(value) {
    return String(value);
  },
  normalize: function (value) {
    return value.trim();
  },
};

function outer() {
  function inner() {
    return helpers.format(4);
  }
  return inner();
}

const View = () => (
  <section>
    <span>content</span>
  </section>
);
