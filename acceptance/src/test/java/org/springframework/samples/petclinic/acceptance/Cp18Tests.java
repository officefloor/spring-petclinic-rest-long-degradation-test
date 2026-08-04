package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp18 city-capacity: Reject creating an owner when the owner's city already contains 50 or more owners. Respond... */
@Tag("cp18")
class Cp18Tests extends AcceptanceBase {

	@Test
	void coreRejectsWhenCityFull() throws Exception {
		// TODO: seed a city to 50 owners, then expect 409
		getOwner(createOwnerOk(ownerNode())); // placeholder create
	}
}
